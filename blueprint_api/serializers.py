from rest_framework import serializers

from .models import Category, Product, ProductVariation, StockEntry, RetailSale, Customer, Order, Supplier, CategoryImage, PriceHistory, SiteConfig

class CategoryImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoryImage
        fields = ['id', 'name', 'image', 'image_url', 'alt_text', 'is_featured', 'display_order', 'created_at']

    def to_representation(self, instance):
        """Override to provide effective image logic for individual collection images"""
        data = super().to_representation(instance)
        
        # Replace 'image' with effective URL (image_url takes precedence) - always fully qualified
        effective_url = None
        if instance.image_url:
            effective_url = instance.image_url
        elif instance.image:
            try:
                effective_url = instance.image.url
            except (AttributeError, ValueError):
                effective_url = None
        
        # Build full URL if it's a relative path
        if effective_url and not effective_url.startswith(('http://', 'https://')):
            request = self.context.get('request')
            if request:
                effective_url = request.build_absolute_uri(effective_url)
        
        data['image'] = effective_url
        
        return data

class CategorySerializer(serializers.ModelSerializer):
    images = CategoryImageSerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'parent', 'image', 'description', 'images']

    def to_representation(self, instance):
        """Override to provide effective image logic"""
        data = super().to_representation(instance)
        
        # Replace 'image' with effective main image URL (always fully qualified)
        effective_url = instance.get_effective_image_url()
        if effective_url and not effective_url.startswith(('http://', 'https://')):
            # Build full URL if it's a relative path
            request = self.context.get('request')
            if request:
                effective_url = request.build_absolute_uri(effective_url)
        data['image'] = effective_url
        
        # Replace 'images' with effective images collection (always fully qualified URLs)
        effective_images = instance.get_effective_images_collection()
        for img_data in effective_images:
            if img_data.get('image') and not img_data['image'].startswith(('http://', 'https://')):
                request = self.context.get('request')
                if request:
                    img_data['image'] = request.build_absolute_uri(img_data['image'])
        data['images'] = effective_images
        
        return data

class CategoryPageProductVariationSerializer(serializers.ModelSerializer):

    def get_effective_image_url(self, obj):
        """Get the effective main image URL (URL field takes precedence, with fallback)"""
        return obj.get_effective_image_url()

    def get_featured_image(self, obj):
        """Get the featured image (either from collection or main image)"""
        featured = obj.get_featured_image()
        if featured:
            if hasattr(featured, 'category'):  # CategoryImage object
                return {
                    'type': 'collection',
                    'id': featured.id,
                    'name': featured.name,
                    'image': featured.image.url if featured.image else None,
                    'image_url': featured.image_url,
                    'effective_image_url': featured.get_effective_image_url(),
                    'alt_text': featured.alt_text,
                    'source': 'url' if featured.image_url else 'file'
                }
            else:  # Main image field (Category object)
                return {
                    'type': 'main',
                    'image': featured.image.url if featured.image else None,
                    'image_url': featured.image_url,
                    'effective_image_url': featured.get_effective_image_url(),
                    'name': 'Main Image',
                    'alt_text': f"{obj.name} main image",
                    'source': 'url' if featured.image_url else 'file'
                }
        return None

    def get_featured_image_url(self, obj):
        """Get just the featured image URL (always returns a URL with fallback)"""
        return obj.get_featured_image_url()

    def get_featured_image_with_fallback(self, obj):
        """Get the featured image with fallback support"""
        featured = obj.get_effective_featured_image()
        if featured:
            # Check if it's a fallback image (dict format)
            if isinstance(featured, dict):
                return featured
            # Handle CategoryImage object
            elif hasattr(featured, 'category'):
                return {
                    'type': 'collection',
                    'id': featured.id,
                    'name': featured.name,
                    'image': featured.image.url if featured.image else None,
                    'image_url': featured.image_url,
                    'effective_image_url': featured.get_effective_image_url(),
                    'alt_text': featured.alt_text,
                    'source': 'url' if featured.image_url else 'file'
                }
            # Handle Category object (main image)
            else:
                return {
                    'type': 'main',
                    'image': featured.image.url if featured.image else None,
                    'image_url': featured.image_url,
                    'effective_image_url': featured.get_effective_image_url(),
                    'name': 'Main Image',
                    'alt_text': f"{obj.name} main image",
                    'source': 'url' if featured.image_url else 'file'
                }
        return None

    def get_total_image_count(self, obj):
        """Get total count of all images"""
        return obj.get_image_count()

    def get_all_images(self, obj):
        """Get all images including main image, collection images, and fallback"""
        all_images = obj.get_all_images()
        result = []
        
        for img_data in all_images:
            image_info = {
                'type': img_data['type'],
                'name': img_data['name'],
                'alt_text': img_data['alt_text'],
                'source': img_data['source']
            }
            
            # Handle different image types
            if img_data['type'] == 'fallback':
                # Fallback images are already processed with URLs
                image_info.update({
                    'image_url': img_data['image_url'],
                    'effective_image_url': img_data['image_url'],
                    'is_featured': True,  # Fallback is featured when no other images exist
                    'product_id': img_data.get('product_id'),
                    'variation_id': img_data.get('variation_id'),
                    'product_name': img_data.get('product_name'),
                    'variation_name': img_data.get('variation_name')
                })
            else:
                # Regular category images
                image_info.update({
                    'is_featured': img_data['is_featured'],
                    'effective_image_url': img_data['image_url']
                })
                
                # Handle uploaded image file URL
                if 'image' in img_data and img_data['image']:
                    try:
                        image_info['image'] = img_data['image'].url
                    except (AttributeError, ValueError):
                        image_info['image'] = str(img_data['image'])
                else:
                    image_info['image'] = None
                
                # Add collection-specific fields
                if img_data['type'] == 'collection':
                    image_info['display_order'] = img_data.get('display_order', 0)
            
            result.append(image_info)
        
        return result

class CategoryPageProductVariationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariation
        fields = ['id', 'name', 'sku', 'price', 'image', 'url']

class CategoryPageProductSerializer(serializers.ModelSerializer):
    variations = CategoryPageProductVariationSerializer(many=True, read_only=True)
    attributes = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'slug', 'categories', 'unit', 'description', 'variations', 'attributes']

    def get_attributes(self, obj):
        """Get product attributes as a dict"""
        result = {}
        for attr in obj.attributes.select_related('category_attribute').prefetch_related('selected_choices').all():
            choices = attr.selected_choices.all()
            if choices:
                # If multiple choices, return as list; if single choice, return as single value
                if len(choices) == 1:
                    result[attr.category_attribute.name] = {
                        'value': choices[0].value,
                        'slug': choices[0].slug
                    }
                else:
                    result[attr.category_attribute.name] = {
                        'values': [{'value': choice.value, 'slug': choice.slug} for choice in choices]
                    }
        return result

class CategoryPageSerializer(serializers.ModelSerializer):
    subcategories = serializers.SerializerMethodField()
    products = serializers.SerializerMethodField()
    images = CategoryImageSerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'parent', 'image', 'description', 'subcategories', 'products', 'images']

    def to_representation(self, instance):
        """Override to provide effective image logic"""
        data = super().to_representation(instance)
        
        # Replace 'image' with effective main image URL (always fully qualified)
        effective_url = instance.get_effective_image_url()
        if effective_url and not effective_url.startswith(('http://', 'https://')):
            # Build full URL if it's a relative path
            request = self.context.get('request')
            if request:
                effective_url = request.build_absolute_uri(effective_url)
        data['image'] = effective_url
        
        # Replace 'images' with effective images collection (always fully qualified URLs)
        effective_images = instance.get_effective_images_collection()
        for img_data in effective_images:
            if img_data.get('image') and not img_data['image'].startswith(('http://', 'https://')):
                request = self.context.get('request')
                if request:
                    img_data['image'] = request.build_absolute_uri(img_data['image'])
        data['images'] = effective_images
        
        return data

    def get_subcategories(self, obj):
        return CategorySerializer(obj.subcategories.all(), many=True).data

    def get_products(self, obj):
        products = Product.objects.filter(categories=obj)
        return CategoryPageProductSerializer(products, many=True).data

class ProductVariationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariation
        fields = ['id', 'product', 'name', 'sku', 'price', 'image']

class ProductVariationLookupSerializer(serializers.ModelSerializer):
    """Serializer for product variation lookup by SKU"""
    class Meta:
        model = ProductVariation
        fields = ['id', 'name', 'sku', 'price']
        lookup_field = 'sku'

class ProductSerializer(serializers.ModelSerializer):
    variations = ProductVariationSerializer(many=True, read_only=True)
    categories = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'categories', 'unit', 'description', 'variations',
            'hero_headline', 'hero_subheadline', 'benefits', 'emotional_pitch', 'testimonials'
        ]

class ProductDetailSerializer(serializers.ModelSerializer):
    """Detailed product serializer with category slugs and full variation info"""
    variations = ProductVariationSerializer(many=True, read_only=True)
    categories = CategorySerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'categories', 'unit', 'description', 'variations', 'created_at',
            'hero_headline', 'hero_subheadline', 'benefits', 'emotional_pitch', 'testimonials'
        ]

class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['id', 'name', 'slug', 'contact_info']

# Lookup serializers for slug-based queries
class CategoryLookupSerializer(serializers.ModelSerializer):
    """Serializer for category lookup by slug"""
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug']
        lookup_field = 'slug'

class ProductLookupSerializer(serializers.ModelSerializer):
    """Serializer for product lookup by slug"""
    class Meta:
        model = Product
        fields = ['id', 'name', 'slug']
        lookup_field = 'slug'

class SupplierLookupSerializer(serializers.ModelSerializer):
    """Serializer for supplier lookup by slug"""
    class Meta:
        model = Supplier
        fields = ['id', 'name', 'slug']
        lookup_field = 'slug'

class StockEntrySerializer(serializers.ModelSerializer):
    supplier = SupplierSerializer(read_only=True)

    class Meta:
        model = StockEntry
        fields = ['id', 'variation', 'quantity', 'unit_price', 'supplier', 'purchase_date', 'receipt_info']

class RetailSaleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RetailSale
        fields = ['id', 'variation', 'quantity', 'retail_price', 'sale_date']

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ['id', 'name', 'raw_address', 'phone', 'district', 'thana']

class CustomerDetailSerializer(serializers.ModelSerializer):
    """Detailed customer serializer with full information"""
    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'raw_address', 'formatted_address', 
            'phone', 'district', 'thana', 'fraud_report_count', 
            'success_count', 'cancellation_count', 'created_at'
        ]

class CustomerLookupSerializer(serializers.ModelSerializer):
    """Serializer for customer lookup by phone"""
    class Meta:
        model = Customer
        fields = ['id', 'name', 'phone']
        lookup_field = 'phone'

class OrderCreateSerializer(serializers.Serializer):
    customer = serializers.DictField()
    product = serializers.DictField()
    quantity = serializers.IntegerField(default=1)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        # Validate customer data
        customer_data = data.get('customer', {})
        required_customer_fields = ['name', 'address', 'phone']
        for field in required_customer_fields:
            if field not in customer_data:
                raise serializers.ValidationError(f"Customer {field} is required")

        # Validate product data
        product_data = data.get('product', {})
        if 'variation' not in product_data or 'id' not in product_data['variation']:
            raise serializers.ValidationError("Product variation ID is required")

        return data

    def create(self, validated_data):
        customer_data = validated_data['customer']
        product_data = validated_data['product']
        variation_id = product_data['variation']['id']

        # Get or create customer based on phone
        customer, created = Customer.objects.get_or_create(
            phone=customer_data['phone'],
            defaults={
                'name': customer_data['name'],
                'raw_address': customer_data['address'],
            }
        )

        # Get product variation
        try:
            variation = ProductVariation.objects.get(id=variation_id)
        except ProductVariation.DoesNotExist:
            raise serializers.ValidationError("Product variation not found")

        # Create order
        order = Order.objects.create(
            customer=customer,
            variation=variation,
            quantity=validated_data.get('quantity', 1),
            notes=validated_data.get('notes', '')
        )

        return order

class OrderSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer(read_only=True)
    product_name = serializers.CharField(source='variation.product.name', read_only=True)
    product_slug = serializers.CharField(source='variation.product.slug', read_only=True)
    variation_name = serializers.CharField(source='variation.name', read_only=True)
    variation_sku = serializers.CharField(source='variation.sku', read_only=True)
    variation_price = serializers.DecimalField(source='variation.price', max_digits=10, decimal_places=2, read_only=True)
    total_amount = serializers.ReadOnlyField()

    class Meta:
        model = Order
        fields = [
            'id', 'customer', 'product_name', 'product_slug', 
            'variation_name', 'variation_sku', 'variation_price', 
            'quantity', 'total_amount', 'status', 'order_date', 'notes'
        ]

# ===============================================
# PRICE ANALYSIS SERIALIZERS
# ===============================================

class PriceHistorySerializer(serializers.ModelSerializer):
    """Serializer for individual price history entries"""
    variation_sku = serializers.CharField(source='variation.sku', read_only=True)
    variation_name = serializers.CharField(source='variation.name', read_only=True)
    product_name = serializers.CharField(source='variation.product.name', read_only=True)

    class Meta:
        model = PriceHistory
        fields = [
            'id', 'variation', 'variation_sku', 'variation_name', 'product_name',
            'price', 'date_time', 'notes'
        ]

class PriceChangeAnalysisSerializer(serializers.Serializer):
    """Serializer for price change analysis data"""
    sku = serializers.CharField()
    product_name = serializers.CharField()
    variation_name = serializers.CharField()
    current_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    previous_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    change_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    change_percent = serializers.FloatField()
    change_type = serializers.CharField()  # 'INCREASE' or 'DECREASE'
    last_change_date = serializers.DateTimeField()
    total_price_entries = serializers.IntegerField()

class PriceDropAnalysisSerializer(serializers.Serializer):
    """Serializer for price drop analysis"""
    sku = serializers.CharField()
    product_name = serializers.CharField()
    variation_name = serializers.CharField()
    current_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    previous_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    drop_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    drop_percent = serializers.FloatField()
    last_change_date = serializers.DateTimeField()

class PriceIncreaseAnalysisSerializer(serializers.Serializer):
    """Serializer for price increase analysis"""
    sku = serializers.CharField()
    product_name = serializers.CharField()
    variation_name = serializers.CharField()
    current_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    previous_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    increase_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    increase_percent = serializers.FloatField()
    last_change_date = serializers.DateTimeField()

class VolatilePriceAnalysisSerializer(serializers.Serializer):
    """Serializer for volatile price analysis"""
    sku = serializers.CharField()
    product_name = serializers.CharField()
    variation_name = serializers.CharField()
    current_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    min_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    max_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    price_range = serializers.DecimalField(max_digits=10, decimal_places=2)
    volatility_percent = serializers.FloatField()
    direction_changes = serializers.IntegerField()
    total_price_entries = serializers.IntegerField()

class PriceAnalysisSummarySerializer(serializers.Serializer):
    """Serializer for overall price analysis summary"""
    total_variations = serializers.IntegerField()
    total_price_histories = serializers.IntegerField()
    variations_with_no_history = serializers.IntegerField()
    variations_with_single_history = serializers.IntegerField()
    variations_with_multiple_history = serializers.IntegerField()
    recent_price_drops = serializers.IntegerField()
    recent_price_increases = serializers.IntegerField()
    days_analyzed = serializers.IntegerField()

class PriceAnalysisRequestSerializer(serializers.Serializer):
    """Serializer for price analysis request parameters"""
    days_back = serializers.IntegerField(default=30, min_value=1, max_value=365)
    min_change_percent = serializers.FloatField(default=1.0, min_value=0.1)
    limit = serializers.IntegerField(default=50, min_value=1, max_value=1000)
    analysis_type = serializers.ChoiceField(
        choices=[
            ('all_changes', 'All Price Changes'),
            ('drops_only', 'Price Drops Only'),
            ('increases_only', 'Price Increases Only'),
            ('volatile_only', 'Volatile Prices Only'),
            ('summary_only', 'Summary Only')
        ],
        default='all_changes'
    )

# ===============================================
# SITE CONFIGURATION SERIALIZER
# ===============================================

class SiteConfigSerializer(serializers.ModelSerializer):
    """Serializer for site-wide configuration settings"""
    
    class Meta:
        model = SiteConfig
        fields = [
            'id', 'cod_enabled', 'free_delivery_text', 'return_policy_text', 
            'authentic_text', 'guarantee_text', 'support_phone', 'support_whatsapp',
            'trust_badges', 'shipping_notice', 'cta_text', 'enable_countdown',
            'countdown_end_date', 'countdown_text', 'enable_stock_counter',
            'stock_counter_text', 'enable_social_proof', 'social_proof_interval'
        ]
        read_only_fields = ['id']

    def to_representation(self, instance):
        """Custom representation to ensure proper data structure"""
        data = super().to_representation(instance)
        
        # Ensure trust_badges is properly formatted
        if not data.get('trust_badges'):
            data['trust_badges'] = []
        
        # Add computed fields for frontend convenience
        data['has_countdown'] = data.get('enable_countdown', False) and data.get('countdown_end_date') is not None
        data['has_whatsapp'] = bool(data.get('support_whatsapp', '').strip())
        
        return data
