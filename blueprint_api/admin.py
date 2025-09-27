from django.contrib import admin
from django.db.models import Sum, F

# Register your models here.
admin.site.site_header = "Bleuprint Admin Panel"
admin.site.site_title = "Bleuprint Admin"
admin.site.index_title = "Welcome to the Dashboard"

import math
from .models import (
    Product, Supplier, StockEntry, RetailSale, ProductVariation, Category, Customer, Order, PriceHistory,
    CategoryAttribute, CategoryAttributeChoice, ProductAttribute, CategoryImage, SiteConfig
)
from .forms import StockEntryForm, RetailSaleForm, OrderEntryForm, ProductAttributeForm

def format_bd_number(n):
    """Format number in lakh/crore style (e.g., 12,34,567)"""
    if n is None:
        return "0"
    s = str(int(n))[::-1]
    parts = [s[:3]] + [s[i:i+2] for i in range(3, len(s), 2)]
    return ','.join(part[::-1] for part in parts[::-1])

def get_current_stock_value(variation):
    entry_data = StockEntry.objects.filter(variation=variation).aggregate(
        total_qty=Sum('quantity'),
        total_cost=Sum(F('quantity') * F('unit_price'))
    )
    total_entries = entry_data['total_qty'] or 0
    total_entry_cost = entry_data['total_cost'] or 0

    sold_qty = RetailSale.objects.filter(variation=variation).aggregate(
        total=Sum('quantity')
    )['total'] or 0

    current_qty = total_entries - sold_qty
    avg_cost = (total_entry_cost / total_entries) if total_entries else 0

    return current_qty * avg_cost


# ---------- Product ----------
class PriceHistoryInline(admin.TabularInline):
    model = PriceHistory
    extra = 1
    fields = ('price', 'date_time', 'notes')
    ordering = ['-date_time']
    readonly_fields = ('date_time',)  # Make date_time read-only after creation

class ProductVariationInline(admin.TabularInline):
    model = ProductVariation
    extra = 5
    fields = ('name', 'sku', 'current_price_display', 'image', 'url')
    readonly_fields = ('current_price_display',)
    show_change_link = True

    def current_price_display(self, obj):
        return f"৳{obj.price}" if obj.price else "No price set"
    current_price_display.short_description = "Current Price"


# ---------- ProductVariation ----------
@admin.register(ProductVariation)
class ProductVariationAdmin(admin.ModelAdmin):
    list_display = ('product_name', 'name', 'current_price', 'current_stock', 'total_stock_value', 'crawl_status', 'crawler_type', 'has_url')
    search_fields = ('sku', 'name', 'product__name')
    list_filter = ('product__categories', 'is_crawling_enabled', 'crawl_error_count')
    inlines = [PriceHistoryInline]
    actions = ['crawl_selected_prices', 'enable_crawling', 'disable_crawling', 'reset_crawl_errors']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('product', 'name', 'sku', 'image', 'description')
        }),
        ('Price Crawling', {
            'fields': ('url', 'is_crawling_enabled', 'last_crawled_at', 'crawl_error_count', 'last_crawl_error'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('last_crawled_at', 'crawl_error_count', 'last_crawl_error')

    def product_name(self, obj):
        return obj.product.name

    def current_price(self, obj):
        return f"৳{obj.price}" if obj.price else "No price"

    def current_stock(self, obj):
        entries = StockEntry.objects.filter(variation=obj).aggregate(
            total=Sum('quantity')
        )['total'] or 0

        sales = RetailSale.objects.filter(variation=obj).aggregate(
            total=Sum('quantity')
        )['total'] or 0

        return round(entries - sales)

    def total_stock_value(self, obj):
        return format_bd_number(get_current_stock_value(obj))
    
    def crawl_status(self, obj):
        return obj.crawl_status_display()
    
    def crawler_type(self, obj):
        """Show which crawler would be used for this variation"""
        from blueprint_api.crawlers import CrawlerFactory
        if obj.url:
            crawler = CrawlerFactory.get_crawler(obj)
            return crawler.__class__.__name__.replace('Crawler', '')
        return "-"
    
    def has_url(self, obj):
        return "✓" if obj.url else "✗"

    def crawl_selected_prices(self, request, queryset):
        """Action to crawl prices for selected variations"""
        from django.core.management import call_command
        from io import StringIO
        from blueprint_api.crawlers import CrawlerFactory
        
        crawled_count = 0
        success_count = 0
        failed_count = 0
        
        for variation in queryset:
            if variation.should_crawl():
                try:
                    # Get appropriate crawler
                    crawler = CrawlerFactory.get_crawler(variation)
                    
                    # Make request
                    import requests
                    session = requests.Session()
                    session.headers.update({
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                    })
                    
                    response = session.get(variation.url, timeout=10)
                    response.raise_for_status()
                    
                    # Extract price
                    price = crawler.extract_price(variation.url, response.text)
                    
                    if price:
                        # Update price history
                        crawler_name = crawler.__class__.__name__
                        variation.add_price(
                            price=price,
                            notes=f'Crawled from admin using {crawler_name}'
                        )
                        variation.update_crawl_success(price)
                        success_count += 1
                    else:
                        variation.update_crawl_error('Could not extract price from URL')
                        failed_count += 1
                        
                    crawled_count += 1
                    
                except Exception as e:
                    variation.update_crawl_error(f'Crawling failed: {str(e)}')
                    failed_count += 1
        
        if crawled_count > 0:
            message = f"Crawled {crawled_count} variations. Success: {success_count}, Failed: {failed_count}"
            self.message_user(request, message)
        else:
            self.message_user(request, "No variations were crawled. Check URLs and crawling settings.")

    def enable_crawling(self, request, queryset):
        """Enable crawling for selected variations"""
        updated = queryset.update(is_crawling_enabled=True)
        self.message_user(request, f"Enabled crawling for {updated} variations.")

    def disable_crawling(self, request, queryset):
        """Disable crawling for selected variations"""
        updated = queryset.update(is_crawling_enabled=False)
        self.message_user(request, f"Disabled crawling for {updated} variations.")

    def reset_crawl_errors(self, request, queryset):
        """Reset crawl error counts for selected variations"""
        updated = queryset.update(crawl_error_count=0, last_crawl_error=None)
        self.message_user(request, f"Reset crawl errors for {updated} variations.")

    product_name.short_description = "Product"
    current_price.short_description = "Current Price"
    current_stock.short_description = "Stock Qty"
    total_stock_value.short_description = "Stock Cost (৳)"
    crawl_status.short_description = "Crawl Status"
    has_url.short_description = "URL"
    
    crawl_selected_prices.short_description = "Crawl prices for selected variations"
    enable_crawling.short_description = "Enable crawling"
    disable_crawling.short_description = "Disable crawling"
    reset_crawl_errors.short_description = "Reset crawl errors"

# ---------- Category Attributes ----------
class CategoryAttributeChoiceInline(admin.TabularInline):
    model = CategoryAttributeChoice
    extra = 3
    fields = ('value', 'display_order')
    ordering = ['display_order', 'value']

@admin.register(CategoryAttribute)
class CategoryAttributeAdmin(admin.ModelAdmin):
    list_display = ('category', 'name', 'is_required', 'choice_count', 'display_order')
    list_filter = ('category', 'is_required')
    search_fields = ('name', 'category__name')
    inlines = [CategoryAttributeChoiceInline]
    ordering = ['category', 'display_order', 'name']

    def choice_count(self, obj):
        return obj.choices.count()
    choice_count.short_description = "Choices"

class CategoryAttributeInline(admin.TabularInline):
    model = CategoryAttribute
    extra = 2
    fields = ('name', 'is_required', 'display_order')
    ordering = ['display_order']

class CategoryImageInline(admin.TabularInline):
    model = CategoryImage
    extra = 3
    fields = ('name', 'image', 'image_url', 'alt_text', 'is_featured', 'display_order')
    ordering = ['display_order']

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'attribute_count', 'product_count', 'image_count', 'crawlable_variations')
    search_fields = ('name',)
    list_filter = ('parent',)
    fields = ('name', 'slug', 'parent', 'image', 'image_url', 'description')
    inlines = [CategoryAttributeInline, CategoryImageInline]
    actions = ['crawl_category_prices']

    def attribute_count(self, obj):
        return obj.attributes.count()
    attribute_count.short_description = "Attributes"

    def product_count(self, obj):
        return obj.products.count()
    product_count.short_description = "Products"

    def image_count(self, obj):
        return obj.get_image_count()
    image_count.short_description = "Images"

    def crawlable_variations(self, obj):
        """Count of variations that can be crawled in this category"""
        from blueprint_api.models import ProductVariation
        count = ProductVariation.objects.filter(
            product__categories=obj,
            is_crawling_enabled=True,
            url__isnull=False,
            crawl_error_count__lt=5
        ).exclude(url__exact='').count()
        return count
    crawlable_variations.short_description = "Crawlable Variations"

    def crawl_category_prices(self, request, queryset):
        """Action to crawl prices for all variations in selected categories"""
        from blueprint_api.crawlers import CrawlerFactory
        import requests
        
        total_crawled = 0
        total_success = 0
        total_failed = 0
        
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        
        for category in queryset:
            # Get variations for this category
            variations = category.products.values_list('variations', flat=True)
            from blueprint_api.models import ProductVariation
            variations = ProductVariation.objects.filter(
                id__in=variations,
                is_crawling_enabled=True,
                url__isnull=False,
                crawl_error_count__lt=5
            ).exclude(url__exact='')[:20]  # Limit to 20 per category to avoid timeouts
            
            category_crawled = 0
            category_success = 0
            category_failed = 0
            
            for variation in variations:
                if variation.should_crawl():
                    try:
                        # Get appropriate crawler
                        crawler = CrawlerFactory.get_crawler(variation)
                        
                        # Make request
                        response = session.get(variation.url, timeout=10)
                        response.raise_for_status()
                        
                        # Extract price
                        price = crawler.extract_price(variation.url, response.text)
                        
                        if price:
                            # Update price history
                            crawler_name = crawler.__class__.__name__
                            variation.add_price(
                                price=price,
                                notes=f'Crawled from category admin using {crawler_name}'
                            )
                            variation.update_crawl_success(price)
                            category_success += 1
                        else:
                            variation.update_crawl_error('Could not extract price from URL')
                            category_failed += 1
                            
                        category_crawled += 1
                        
                    except Exception as e:
                        variation.update_crawl_error(f'Crawling failed: {str(e)}')
                        category_failed += 1
            
            total_crawled += category_crawled
            total_success += category_success
            total_failed += category_failed
        
        if total_crawled > 0:
            message = f"Crawled {total_crawled} variations across {queryset.count()} categories. Success: {total_success}, Failed: {total_failed}"
            self.message_user(request, message)
        else:
            self.message_user(request, "No variations were crawled. Check if categories have crawlable variations.")

    crawl_category_prices.short_description = "Crawl prices for variations in selected categories"

@admin.register(CategoryImage)
class CategoryImageAdmin(admin.ModelAdmin):
    list_display = ('category', 'name', 'is_featured', 'display_order', 'created_at')
    list_filter = ('category', 'is_featured', 'created_at')
    search_fields = ('category__name', 'name', 'alt_text')
    ordering = ['category', 'display_order', 'created_at']
    fields = ('category', 'name', 'image', 'image_url', 'alt_text', 'is_featured', 'display_order')

# ---------- Product Attributes ----------
class ProductAttributeInline(admin.TabularInline):
    form = ProductAttributeForm
    model = ProductAttribute
    extra = 0
    fields = ('category_attribute', 'selected_choices')
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if hasattr(request, '_obj_') and request._obj_:
            product = request._obj_
            
            if db_field.name == "category_attribute":
                # Only show attributes from product's categories
                category_ids = product.categories.values_list('id', flat=True)
                kwargs["queryset"] = CategoryAttribute.objects.filter(
                    category__in=category_ids
                ).select_related('category')
                
            elif db_field.name == "selected_choices":
                # Only show choices for attributes from product's categories
                category_ids = product.categories.values_list('id', flat=True)
                kwargs["queryset"] = CategoryAttributeChoice.objects.filter(
                    attribute__category__in=category_ids
                ).select_related('attribute')
                
        else:
            # For new products (no categories yet), show empty queryset
            if db_field.name == "category_attribute":
                kwargs["queryset"] = CategoryAttribute.objects.none()
            elif db_field.name == "selected_choices":
                kwargs["queryset"] = CategoryAttributeChoice.objects.none()
                
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'unit', 'category_list', 'attribute_summary', 'variation_count', 'created_at')
    search_fields = ('name', 'description')
    list_filter = ('unit', 'categories', 'created_at')
    filter_horizontal = ('categories',)
    inlines = [ProductAttributeInline, ProductVariationInline]

    def get_form(self, request, obj=None, **kwargs):
        # Store the object in request for use in inlines
        request._obj_ = obj
        return super().get_form(request, obj, **kwargs)

    def category_list(self, obj):
        return ", ".join([cat.name for cat in obj.categories.all()])
    category_list.short_description = "Categories"

    def attribute_summary(self, obj):
        attrs = obj.get_all_attributes()
        if attrs:
            return ", ".join([f"{k}: {v}" for k, v in list(attrs.items())[:3]])
        return "No attributes"
    attribute_summary.short_description = "Attributes"

    def variation_count(self, obj):
        return obj.variations.count()
    variation_count.short_description = "Variations"

# ---------- Supplier ----------
@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name', 'slug', 'contact_info')
    prepopulated_fields = {'slug': ('name',)}

# ---------- Stock Entry ----------
@admin.register(StockEntry)
class StockEntryAdmin(admin.ModelAdmin):
    form = StockEntryForm
    list_display = ('variation', 'quantity', 'unit_price', 'supplier', 'purchase_date')
    list_filter = ('supplier', 'purchase_date')
    search_fields = ('variation__product__name', 'variation__name')

# ---------- Retail Sale ----------
@admin.register(RetailSale)
class RetailSaleAdmin(admin.ModelAdmin):
    form = RetailSaleForm
    list_display = ('variation', 'quantity', 'retail_price', 'sale_date')
    list_filter = ('sale_date',)
    search_fields = ('variation__product__name', 'variation__name')

# ---------- Customer ----------
@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'district', 'thana', 'success_count', 'fraud_report_count')
    list_filter = ('district', 'thana', 'fraud_report_count')
    search_fields = ('name', 'phone', 'raw_address')

# ---------- Order ----------
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = OrderEntryForm
    list_display = ('id', 'customer', 'variation', 'quantity', 'status', 'total_amount', 'order_date')
    list_filter = ('status', 'order_date')
    search_fields = ('customer__name', 'customer__phone', 'variation__product__name', 'variation__name')

# ---------- Price History ----------
@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ('variation_sku', 'variation_name', 'price', 'date_time', 'notes')
    list_filter = ('date_time', 'variation__product__categories')
    search_fields = ('variation__sku', 'variation__name', 'variation__product__name')
    ordering = ['-date_time']
    
    def variation_sku(self, obj):
        return obj.variation.sku
    
    def variation_name(self, obj):
        return f"{obj.variation.product.name} - {obj.variation.name}"
    
    variation_sku.short_description = "SKU"
    variation_name.short_description = "Product Variation"

# ---------- Site Configuration ----------
@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    """Admin for site-wide configuration"""
    
    def has_add_permission(self, request):
        """Only allow one instance of SiteConfig"""
        return not SiteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of the singleton instance"""
        return False

    fieldsets = (
        ('Delivery & Payment Settings', {
            'fields': ('cod_enabled', 'free_delivery_text', 'shipping_notice'),
            'description': 'Configure delivery and payment options'
        }),
        ('Trust & Guarantee Elements', {
            'fields': ('return_policy_text', 'authentic_text', 'guarantee_text'),
            'description': 'Build customer confidence with trust signals'
        }),
        ('Contact Information', {
            'fields': ('support_phone', 'support_whatsapp'),
            'description': 'Customer support contact details'
        }),
        ('Call-to-Action', {
            'fields': ('cta_text',),
            'description': 'Button text for purchases'
        }),
        ('Urgency & Scarcity Features', {
            'fields': (
                'enable_countdown', 'countdown_end_date', 'countdown_text',
                'enable_stock_counter', 'stock_counter_text'
            ),
            'classes': ('collapse',),
            'description': 'Features to create urgency and scarcity'
        }),
        ('Social Proof Settings', {
            'fields': ('enable_social_proof', 'social_proof_interval'),
            'classes': ('collapse',),
            'description': 'Settings for social proof notifications'
        }),
        ('Trust Badges (JSON)', {
            'fields': ('trust_badges',),
            'classes': ('collapse',),
            'description': 'Trust badges/icons in JSON format: [{"name": "Badge Name", "icon": "icon-class", "text": "Badge text"}]'
        }),
    )

    def changelist_view(self, request, extra_context=None):
        """Redirect to the single instance edit page"""
        config = SiteConfig.objects.get_config()
        return self.change_view(request, str(config.pk), extra_context)

    def add_view(self, request, form_url='', extra_context=None):
        """Redirect add to edit if instance exists"""
        if SiteConfig.objects.exists():
            config = SiteConfig.objects.get_config()
            return self.change_view(request, str(config.pk), extra_context)
        return super().add_view(request, form_url, extra_context)