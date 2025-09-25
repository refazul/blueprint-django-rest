from django import forms
from django_select2.forms import ModelSelect2Widget, ModelSelect2MultipleWidget

from .models import Product, Supplier, StockEntry, RetailSale, ProductVariation, Order, Customer, ProductAttribute, CategoryAttribute, CategoryAttributeChoice

class CategoryAttributeChoiceWidget(ModelSelect2Widget):
    """Custom widget that filters choices by attribute"""
    
    model = CategoryAttributeChoice  # ✅ Explicitly set the model
    
    def filter_queryset(self, request, term, queryset=None, **dependent_fields):
        """Override to filter choices by selected attribute"""
        if queryset is None:
            queryset = self.model.objects.all()
        
        # Debug: Print all available data
        print(f"DEBUG: dependent_fields = {dependent_fields}")
        
        # Get the category_attribute value from dependent_fields
        category_attribute_id = dependent_fields.get('category_attribute')
        print(f"DEBUG: category_attribute_id from dependent_fields: {category_attribute_id}")
        
        # Filter by attribute if we have one
        if category_attribute_id:
            try:
                # Debug: Check what's in the database
                #all_choices = CategoryAttributeChoice.objects.all()
                #print(f"DEBUG: Total choices in database: {all_choices.count()}")
                
                # Check if any choices exist for this attribute
                #choices_for_attr = CategoryAttributeChoice.objects.filter(attribute=category_attribute_id)
                #print(f"DEBUG: Choices for attribute {category_attribute_id}: {choices_for_attr.count()}")
                
                # Debug: Show some sample choices and their attribute IDs
                #sample_choices = all_choices[:5]
                #for choice in sample_choices:
                #    print(f"DEBUG: Choice '{choice.value}' belongs to attribute ID {choice.attribute.id}")
                
                # Apply the filter to queryset
                queryset = CategoryAttributeChoice.objects.filter(attribute=category_attribute_id)
                print(f"DEBUG: Final filtered queryset: {queryset.count()} choices")
                
                # Debug: Show what we actually got
                #if queryset.exists():
                #    for choice in queryset[:3]:
                #        print(f"DEBUG: Filtered choice: '{choice.value}' (ID: {choice.id})")

            except (ValueError, TypeError) as e:
                print(f"DEBUG: Error filtering queryset: {e}")
                queryset = queryset.none()
        else:
            print("DEBUG: No category_attribute_id found, returning empty queryset")
            queryset = queryset.none()  # Return empty if no attribute selected
        
        # Apply search term filtering
        if term:
            queryset = queryset.filter(value__icontains=term)
            print(f"DEBUG: Applied term filter '{term}', now {queryset.count()} choices")
        
        return queryset

class CategoryAttributeChoiceMultipleWidget(ModelSelect2MultipleWidget):
    """Custom widget that filters choices by attribute for multiple selection"""
    
    model = CategoryAttributeChoice  # ✅ Explicitly set the model
    
    def filter_queryset(self, request, term, queryset=None, **dependent_fields):
        """Override to filter choices by selected attribute"""
        if queryset is None:
            queryset = self.model.objects.all()

        # Debug: Print all available data
        print(f"DEBUG: dependent_fields = {dependent_fields}")
        
        # Get the category_attribute value from dependent_fields
        category_attribute_id = dependent_fields.get('category_attribute')

        # Debug:
        print(f"DEBUG: category_attribute_id from dependent_fields: {category_attribute_id}")
        
        # Filter by attribute if we have one
        if category_attribute_id:
            try:
                # Debug: Check what's in the database
                all_choices = CategoryAttributeChoice.objects.all()
                print(f"DEBUG: Total choices in database: {all_choices.count()}")
                
                # Check if any choices exist for this attribute
                choices_for_attr = CategoryAttributeChoice.objects.filter(attribute=category_attribute_id)
                print(f"DEBUG: Choices for attribute {category_attribute_id}: {choices_for_attr.count()}")
                
                # Debug: Show some sample choices and their attribute IDs
                sample_choices = choices_for_attr
                for choice in sample_choices:
                    print(f"DEBUG: Choice '{choice.value}' belongs to attribute ID {choice.attribute.id}")
                queryset = CategoryAttributeChoice.objects.filter(attribute=category_attribute_id)
            except (ValueError, TypeError) as e:
                queryset = queryset.none()
        else:
            queryset = queryset.none()  # Return empty if no attribute selected
        
        print(f"DEBUG: queryset {queryset}")
        # Apply search term filtering
        if term:
            queryset = queryset.filter(value__icontains=term)
        
        print(f"DEBUG: {term} queryset {queryset}")

        return queryset

class ProductAttributeForm(forms.ModelForm):
    class Meta:
        model = ProductAttribute
        fields = '__all__'
        widgets = {
            'category_attribute': ModelSelect2Widget(
                model=CategoryAttribute,
                search_fields=['name__icontains', 'slug__icontains'],
                attrs={
                    'data-minimum-input-length': 0,  # ✅ show on focus
                    'id': 'id_category_attribute'  # Ensure consistent ID
                }
            ),
            'selected_choices': CategoryAttributeChoiceMultipleWidget(
                model=CategoryAttributeChoice,
                search_fields=['value__icontains', 'slug__icontains'],
                dependent_fields={'category_attribute': 'category_attribute'},  # ✅ Set up dependency
                attrs={
                    'data-minimum-input-length': 0  # ✅ show on focus
                }
            )
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Don't restrict the queryset here - let the widget handle filtering
        # The widget will filter choices dynamically based on the selected attribute
        # Setting queryset to .none() causes validation issues
        pass
    
    def clean_selected_choices(self):
        """Custom validation for selected_choices field"""
        selected_choices = self.cleaned_data.get('selected_choices')
        category_attribute = self.cleaned_data.get('category_attribute')
        
        print(f"DEBUG clean_selected_choices: category_attribute = {category_attribute}")
        print(f"DEBUG clean_selected_choices: selected_choices = {selected_choices}")
        
        if not category_attribute:
            # If no category_attribute is selected yet, we can't validate choices
            print("DEBUG: No category_attribute selected, skipping validation")
            return selected_choices
        
        # Validate that all selected choices belong to the selected category attribute
        if selected_choices:
            print(f"DEBUG: Submitted choice IDs: {[choice.id for choice in selected_choices]}")
            
            for choice in selected_choices:
                print(f"DEBUG: Checking choice {choice.id}:{choice.value} - attribute ID: {choice.attribute.id}")
                if choice.attribute.id != category_attribute.id:
                    print(f"DEBUG: INVALID choice {choice.id}:{choice.value}")
                    raise forms.ValidationError(
                        f"Choice '{choice.value}' does not belong to attribute '{category_attribute.name}'"
                    )
                else:
                    print(f"DEBUG: VALID choice {choice.id}:{choice.value}")
        
        print(f"DEBUG: All choices are valid, returning {selected_choices}")
        return selected_choices
    
    def save(self, commit=True):
        """Custom save method to handle ManyToMany relationship properly"""
        instance = super().save(commit=False)
        
        if commit:
            instance.save()
            # Now handle the ManyToMany field
            self.save_m2m()
            
        return instance
    
    def clean(self):
        """Clean method for any additional validation"""
        cleaned_data = super().clean()
        # The individual field validation in clean_selected_choices is sufficient
        # No need for additional validation here
        return cleaned_data

class RetailSaleForm(forms.ModelForm):
    class Meta:
        model = RetailSale
        fields = '__all__'
        widgets = {
            'variation': ModelSelect2Widget(
                model=ProductVariation,
                search_fields=['name__icontains', 'sku__icontains', 'product__name__icontains'],
                attrs={
                    'data-minimum-input-length': 0  # ✅ show on focus
                }
            )
        }

class StockEntryForm(forms.ModelForm):
    class Meta:
        model = StockEntry
        fields = '__all__'
        widgets = {
            'variation': ModelSelect2Widget(
                model=ProductVariation,
                search_fields=['name__icontains', 'sku__icontains', 'product__name__icontains'],
                attrs={
                    'data-minimum-input-length': 0  # ✅ show on focus
                }
            ),
            'supplier': ModelSelect2Widget(
                model=Supplier,
                search_fields=['name__icontains', 'contact_info__icontains'],
                attrs={
                    'data-minimum-input-length': 0  # ✅ show on focus
                }
            )
        }

class OrderEntryForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = '__all__'
        widgets = {
            'variation': ModelSelect2Widget(
                model=ProductVariation,
                search_fields=['name__icontains', 'sku__icontains', 'product__name__icontains'],
                attrs={
                    'data-minimum-input-length': 0  # ✅ show on focus
                }
            ),
            'customer': ModelSelect2Widget(
                model=Customer,
                search_fields=['name__icontains', 'contact_info__icontains'],
                attrs={
                    'data-minimum-input-length': 0  # ✅ show on focus
                }
            )
        }