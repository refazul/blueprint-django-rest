# models.py

from django.db import models
from django.utils.text import slugify
from django.utils import timezone
import re
import random
from .storages import PassthroughURLStorage

def aggressive_slugify(text, max_length=100):
    """More aggressive slugify that handles special characters better"""
    if not text:
        return ""
    
    # Convert to string and lowercase
    text = str(text).lower()
    
    # Replace common words/phrases for better slugs
    replacements = {
        'processor': 'cpu',
        'generation': 'gen',
        'storage': 'storage',
        'connectivity': 'conn',
        'gigabyte': 'gb',
        'terabyte': 'tb',
        'megabyte': 'mb',
        'cellular': 'cell',
        'bluetooth': 'bt',
        'wireless': 'wifi',
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # Remove special characters and extra spaces
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    
    # Use Django's slugify for final cleanup
    slug = slugify(text)
    
    # Truncate if too long
    if len(slug) > max_length:
        slug = slug[:max_length].rstrip('-')
    
    return slug

# ---------- Category Attributes ----------
class CategoryAttributeManager(models.Manager):
    def get_by_natural_key(self, slug):
        return self.get(slug=slug)

class CategoryAttribute(models.Model):
    category = models.ForeignKey('Category', on_delete=models.CASCADE, related_name='attributes')
    name = models.CharField(max_length=100)  # e.g., "Processor", "Storage", "Color"
    slug = models.SlugField(max_length=150, unique=True)  # e.g., "apple-ipad-cpu", "processors-socket"
    is_required = models.BooleanField(default=False)  # Whether products must have this attribute
    display_order = models.PositiveIntegerField(default=0)  # For ordering in forms/display

    objects = CategoryAttributeManager()

    def save(self, *args, **kwargs):
        if not self.slug:
            # Create slug with category prefix
            category_slug = aggressive_slugify(self.category.slug, 50)
            attr_slug = aggressive_slugify(self.name, 50)
            base_slug = f"{category_slug}-{attr_slug}"
            
            # Ensure uniqueness
            counter = 1
            self.slug = base_slug
            while CategoryAttribute.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{base_slug}-{counter}"
                counter += 1
                
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.category.name} - {self.name}"

    def natural_key(self):
        return (self.slug,)
    natural_key.dependencies = ['scffold_api.category']

    class Meta:
        unique_together = ('category', 'name')  # Remove slug from unique_together since it's globally unique
        ordering = ['display_order', 'name']

class CategoryAttributeChoiceManager(models.Manager):
    def get_by_natural_key(self, slug):
        return self.get(slug=slug)

class CategoryAttributeChoice(models.Model):
    attribute = models.ForeignKey(CategoryAttribute, on_delete=models.CASCADE, related_name='choices')
    value = models.CharField(max_length=200)  # e.g., "A13", "A14", "A15", "64GB", "128GB"
    slug = models.SlugField(max_length=200, unique=True)  # e.g., "apple-ipad-cpu-a13", "apple-ipad-storage-64gb"
    display_order = models.PositiveIntegerField(default=0)

    objects = CategoryAttributeChoiceManager()

    def save(self, *args, **kwargs):
        if not self.slug:
            # Create slug with attribute prefix (which already has category prefix)
            attr_slug = self.attribute.slug
            value_slug = aggressive_slugify(self.value, 50)
            base_slug = f"{attr_slug}-{value_slug}"
            
            # Ensure uniqueness
            counter = 1
            self.slug = base_slug
            while CategoryAttributeChoice.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{base_slug}-{counter}"
                counter += 1
                
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.attribute.name}: {self.value}"

    def natural_key(self):
        return (self.slug,)
    natural_key.dependencies = ['scffold_api.categoryattribute']

    class Meta:
        unique_together = ('attribute', 'value')  # Remove slug from unique_together
        ordering = ['display_order', 'value']

# ---------- Updated Category ----------
class CategoryManager(models.Manager):
    def get_by_natural_key(self, slug):
        return self.get(slug=slug)

class Category(models.Model):
    name = models.CharField(max_length=500)
    slug = models.SlugField(max_length=500, unique=True, blank=True)
    parent = models.ForeignKey('self', null=True, blank=True, related_name='subcategories', on_delete=models.CASCADE)
    # Main category image
    image = models.ImageField(
        upload_to='categories/',
        storage=PassthroughURLStorage(),
        max_length=600,
        blank=True,
        null=True,
        help_text="Main category image (uploaded file)"
    )
    image_url = models.URLField(
        max_length=600,
        blank=True,
        null=True,
        help_text="Main category image URL (takes precedence over uploaded file)"
    )
    description = models.TextField(blank=True, null=True, help_text="Category description")

    objects = CategoryManager()

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
            # Handle duplicate slugs
            counter = 1
            original_slug = self.slug
            while Category.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)

    def get_effective_image_url(self):
        """Get the effective main image URL: image_url > image_file > random product image"""
        # Priority 1: Direct URL
        if self.image_url:
            return self.image_url
        
        # Priority 2: Uploaded file
        if self.image:
            try:
                return self.image.url
            except (AttributeError, ValueError):
                pass
        
        # Priority 3: Fallback to random product image
        fallback_image = self.get_random_product_image()
        if fallback_image:
            return fallback_image
        
        return None

    def get_effective_images_collection(self):
        """Get effective images collection: all image_urls and image_files > if empty, 3 random product images"""
        effective_images = []
        
        # Collect all category images (both URL and file-based)
        for img in self.images.all():
            if img.image_url:
                effective_images.append({
                    'id': img.id,
                    'name': img.name,
                    'image': img.image_url,
                    'alt_text': img.alt_text,
                    'is_featured': img.is_featured,
                    'display_order': img.display_order,
                    'created_at': img.created_at,
                    'source': 'url'
                })
            elif img.image:
                try:
                    effective_images.append({
                        'id': img.id,
                        'name': img.name,
                        'image': img.image.url,
                        'alt_text': img.alt_text,
                        'is_featured': img.is_featured,
                        'display_order': img.display_order,
                        'created_at': img.created_at,
                        'source': 'file'
                    })
                except (AttributeError, ValueError):
                    pass
        
        # If no category images exist, get 3 random product images as fallback
        if not effective_images:
            fallback_images = self.get_random_product_images(count=3)
            for i, img_url in enumerate(fallback_images):
                effective_images.append({
                    'id': f"fallback_{i}",
                    'name': f"Product Image {i+1}",
                    'image': img_url,
                    'alt_text': f"{self.name} product image",
                    'is_featured': i == 0,  # First one is featured
                    'display_order': i,
                    'created_at': None,
                    'source': 'fallback'
                })
        
        return effective_images

    def get_all_attributes(self):
        """Get all attributes including inherited from parent categories"""
        attributes = list(self.attributes.all())
        
        # Add parent category attributes if any
        if self.parent:
            parent_attributes = self.parent.get_all_attributes()
            # Avoid duplicates by checking attribute names
            existing_names = {attr.name for attr in attributes}
            for parent_attr in parent_attributes:
                if parent_attr.name not in existing_names:
                    attributes.append(parent_attr)
        
        return attributes

    def get_featured_image(self):
        """Get the featured image for this category"""
        featured = self.images.filter(is_featured=True).first()
        if featured:
            return featured
        # If no featured image, return the first image or the main image
        first_image = self.images.first()
        if first_image:
            return first_image
        # Return main image field if no collection images and has effective URL
        if self.get_effective_image_url():
            return self
        return None

    def get_featured_image_url(self):
        """Get the featured image URL, always returns a URL (with fallback if needed)"""
        featured = self.get_featured_image()
        if featured:
            if hasattr(featured, 'category'):  # CategoryImage object
                return featured.get_effective_image_url()
            else:  # Category object (main image)
                return featured.get_effective_image_url()
        
        # Final fallback - try to get any effective image URL
        return self.get_effective_image_url()

    def get_all_images(self):
        """Get all images for this category including the main image and fallback"""
        images = []
        
        # Add main image if exists (either URL or file)
        effective_main_url = self.get_effective_image_url()
        if effective_main_url:
            images.append({
                'type': 'main',
                'image_url': effective_main_url,
                'image': self.image,
                'name': 'Main Image',
                'alt_text': f"{self.name} main image",
                'is_featured': not self.images.filter(is_featured=True).exists(),
                'source': 'url' if self.image_url else 'file'
            })
        
        # Add collection images
        for img in self.images.all():
            effective_img_url = img.get_effective_image_url()
            if effective_img_url:
                images.append({
                    'type': 'collection',
                    'image_url': effective_img_url,
                    'image': img.image,
                    'name': img.name,
                    'alt_text': img.alt_text or f"{self.name} - {img.name}",
                    'is_featured': img.is_featured,
                    'display_order': img.display_order,
                    'source': 'url' if img.image_url else 'file'
                })
        
        # Add fallback image if no category images exist
        if not images:
            fallback = self.get_fallback_product_image()
            if fallback:
                images.append(fallback)
        
        return images

    def get_image_count(self):
        """Get total count of all images (main + collection)"""
        count = self.images.count()
        if self.get_effective_image_url():
            count += 1
        return count

    def get_random_product_image(self):
        """Get a single random product image URL from products in this category"""
        random_images = self.get_random_product_images(count=1)
        return random_images[0] if random_images else None

    def get_random_product_images(self, count=3):
        """Get multiple random product image URLs from products in this category"""
        from django.db.models import Q
        
        # Get all product variations with images from this category
        variations_with_images = ProductVariation.objects.filter(
            product__categories=self
        ).exclude(
            image=''
        ).exclude(
            image__isnull=True
        )
        
        if not variations_with_images.exists():
            return []
        
        # Use the modular selection strategy
        strategy = self.get_fallback_image_selection_strategy()
        selected_variations = []
        
        # Get multiple variations using the strategy
        available_variations = list(variations_with_images)
        for _ in range(min(count, len(available_variations))):
            if available_variations:
                selected = strategy(available_variations)
                if selected:
                    selected_variations.append(selected)
                    available_variations.remove(selected)
        
        # Extract image URLs from product variation images only
        image_urls = []
        for variation in selected_variations:
            if variation.image:
                try:
                    image_urls.append(variation.image.url)
                except (AttributeError, ValueError):
                    pass
        
        return image_urls

    def get_fallback_image_selection_strategy(self):
        """
        Define the strategy for selecting fallback images from products.
        This method can be overridden or modified to implement custom rules.
        
        Returns a function that takes a queryset of ProductVariations and returns one variation.
        """
        def random_selection(variations_queryset):
            """Random selection strategy"""
            variations_list = list(variations_queryset)
            if variations_list:
                return random.choice(variations_list)
            return None
        
        # You can extend this to support different strategies:
        # def newest_product_selection(variations_queryset):
        #     return variations_queryset.order_by('-product__created_at').first()
        #
        # def most_expensive_selection(variations_queryset):
        #     return variations_queryset.annotate(
        #         latest_price=Subquery(
        #             PriceHistory.objects.filter(variation=OuterRef('pk'))
        #             .order_by('-date_time').values('price')[:1]
        #         )
        #     ).order_by('-latest_price').first()
        
        return random_selection

    def get_fallback_product_image(self):
        """
        Get a fallback image from products in this category and its subcategories.
        Uses the strategy defined in get_fallback_image_selection_strategy().
        """
        # Get all descendant categories (including self)
        descendant_categories = self._get_descendant_categories()
        
        # Get product variations with images from these categories
        from .models import ProductVariation  # Import here to avoid circular imports
        variations_with_images = ProductVariation.objects.filter(
            product__categories__in=descendant_categories,
            image__isnull=False
        ).exclude(image='').select_related('product')
        
        if not variations_with_images.exists():
            return None
        
        # Use the selection strategy to pick a variation
        selection_strategy = self.get_fallback_image_selection_strategy()
        selected_variation = selection_strategy(variations_with_images)
        
        if selected_variation and selected_variation.image:
            return {
                'type': 'fallback',
                'image_url': selected_variation.image.url,
                'name': f"Fallback from {selected_variation.product.name}",
                'alt_text': f"{self.name} category fallback image from {selected_variation.product.name}",
                'source': 'product_fallback',
                'product_id': selected_variation.product.id,
                'variation_id': selected_variation.id,
                'product_name': selected_variation.product.name,
                'variation_name': selected_variation.name
            }
        
        return None

    def _get_descendant_categories(self):
        """
        Get all descendant categories (including self) for fallback image search.
        This is a helper method to get categories at multiple levels.
        """
        from django.db.models import Q
        
        # Start with self
        descendants = [self]
        
        # Get direct children
        children = list(self.subcategories.all())
        descendants.extend(children)
        
        # Get grandchildren (2 levels deep should be enough for most cases)
        for child in children:
            grandchildren = list(child.subcategories.all())
            descendants.extend(grandchildren)
        
        return descendants

    def get_effective_featured_image(self):
        """
        Get the featured image with fallback support.
        Priority: featured collection image > first collection image > main image > fallback product image
        """
        # Try to get the regular featured image first
        featured = self.get_featured_image()
        if featured:
            return featured
        
        # If no category images, try fallback from products
        fallback = self.get_fallback_product_image()
        if fallback:
            return fallback
        
        return None

    def __str__(self):
        return self.name

    def natural_key(self):
        return (self.slug,)
    natural_key.dependencies = []  # no FK inside the natural key

    class Meta:
        verbose_name = "Category"
        verbose_name_plural = "Categories"

# ---------- Category Images ----------
class CategoryImageManager(models.Manager):
    def get_by_natural_key(self, category_slug, image_name):
        return self.get(category__slug=category_slug, name=image_name)

class CategoryImage(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='images')
    name = models.CharField(max_length=200, help_text="Descriptive name for the image")
    image = models.ImageField(
        upload_to='categories/',
        storage=PassthroughURLStorage(),
        max_length=600,
        blank=True,
        null=True,
        help_text="Category image file (uploaded file)"
    )
    image_url = models.URLField(
        max_length=600,
        blank=True,
        null=True,
        help_text="Category image URL (takes precedence over uploaded file)"
    )
    alt_text = models.CharField(max_length=300, blank=True, null=True, help_text="Alternative text for accessibility")
    display_order = models.PositiveIntegerField(default=0, help_text="Order for displaying images")
    is_featured = models.BooleanField(default=False, help_text="Mark as featured image for the category")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CategoryImageManager()

    def save(self, *args, **kwargs):
        # If this is marked as featured, remove featured status from other images in this category
        if self.is_featured:
            CategoryImage.objects.filter(
                category=self.category, 
                is_featured=True
            ).exclude(pk=self.pk).update(is_featured=False)
        super().save(*args, **kwargs)

    def get_effective_image_url(self):
        """Get the effective image URL with fallback, prioritizing image_url over image field, then fallback to product images"""
        if self.image_url:
            return self.image_url
        elif self.image:
            try:
                return self.image.url
            except (AttributeError, ValueError):
                pass
        
        # Fallback to category's fallback mechanism if no image URL available
        fallback_image = self.category.get_fallback_product_image()
        if fallback_image:
            return fallback_image.get('image_url')
        
        return None

    def __str__(self):
        return f"{self.category.name} - {self.name}"

    def natural_key(self):
        return (self.category.slug, self.name)
    natural_key.dependencies = ['scffold_api.category']

    class Meta:
        unique_together = ('category', 'name')
        ordering = ['display_order', 'created_at']
        verbose_name = "Category Image"
        verbose_name_plural = "Category Images"

# ---------- Product Attributes ----------
class ProductAttribute(models.Model):
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='attributes')
    category_attribute = models.ForeignKey(CategoryAttribute, on_delete=models.CASCADE)
    selected_choices = models.ManyToManyField(CategoryAttributeChoice, related_name='product_attributes')

    def __str__(self):
        choices = ", ".join([choice.value for choice in self.selected_choices.all()[:3]])
        if self.selected_choices.count() > 3:
            choices += "..."
        return f"{self.product.name} - {self.category_attribute.name}: {choices}"

    class Meta:
        unique_together = ('product', 'category_attribute')  # One attribute instance per product

# ---------- Updated Product ----------
class ProductManager(models.Manager):
    def get_by_natural_key(self, slug):
        return self.get(slug=slug)

class Product(models.Model):
    UNIT_CHOICES = [
        ('pc', 'পিস'),
        ('kg', 'কেজি'),
        ('ltr', 'লিটার'),
        ('gm', 'গ্রাম'),
        ('yd', 'গজ'),
        ('m', 'মিটার'),
        ('cm', 'সেন্টিমিটার'),
        ('mm', 'মিলিমিটার'),
    ]
    name = models.CharField(max_length=500)
    slug = models.SlugField(max_length=500, unique=True, blank=True)
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default='pc')
    categories = models.ManyToManyField(Category, related_name='products')
    description = models.TextField(blank=True)
    created_at = models.DateField(auto_now_add=True)
    
    # Landing page specific fields
    hero_headline = models.CharField(max_length=150, blank=True, default="", help_text="Main headline for product landing page")
    hero_subheadline = models.CharField(max_length=220, blank=True, default="", help_text="Supporting subheadline for product landing page")
    benefits = models.JSONField(
        default=list, 
        blank=True, 
        help_text="List of product benefits. Format: [{'title': 'Benefit Title', 'description': 'Benefit description'}]"
    )
    emotional_pitch = models.TextField(blank=True, default="", help_text="Emotional appeal text to connect with customers")
    testimonials = models.JSONField(
        default=list, 
        blank=True, 
        help_text="Customer testimonials. Format: [{'name': 'Customer Name', 'text': 'Testimonial text', 'rating': 5, 'location': 'Dhaka'}]"
    )

    objects = ProductManager()

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
            counter = 1
            original_slug = self.slug
            while Product.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)

    def get_attribute_value(self, attribute_name):
        """Get the value(s) of a specific attribute"""
        try:
            product_attr = self.attributes.prefetch_related('selected_choices').get(
                category_attribute__name=attribute_name
            )
            choices = list(product_attr.selected_choices.all())
            if len(choices) == 1:
                return choices[0].value
            else:
                return [choice.value for choice in choices]
        except ProductAttribute.DoesNotExist:
            return None

    def get_all_attributes(self):
        """Get all attributes for this product as a dict"""
        result = {}
        for attr in self.attributes.prefetch_related('selected_choices').all():
            choices = list(attr.selected_choices.all())
            if len(choices) == 1:
                result[attr.category_attribute.name] = choices[0].value
            else:
                result[attr.category_attribute.name] = [choice.value for choice in choices]
        return result

    def __str__(self):
        return f"{self.name}"

    def natural_key(self):
        return (self.slug,)

# ---------- SiteConfig (Singleton) ----------
class SiteConfigManager(models.Manager):
    def get_config(self):
        """Get or create the single SiteConfig instance"""
        obj, created = self.get_or_create(pk=1)
        return obj

class SiteConfig(models.Model):
    """Singleton model for site-wide configuration"""
    
    # COD and delivery settings
    cod_enabled = models.BooleanField(default=True, help_text="Enable Cash on Delivery")
    free_delivery_text = models.CharField(
        max_length=160, 
        default="ফ্রি ডেলিভারি + ক্যাশ অন ডেলিভারি",
        help_text="Text to display for free delivery offer"
    )
    return_policy_text = models.CharField(
        max_length=160, 
        default="পছন্দ না হলে সহজ রিটার্ন",
        help_text="Return policy text"
    )
    authentic_text = models.CharField(
        max_length=160, 
        default="১০০% আসল প্রোডাক্ট, গ্যারান্টি সহ",
        help_text="Authenticity guarantee text"
    )
    guarantee_text = models.CharField(
        max_length=160, 
        default="৭ দিনের রিপ্লেসমেন্ট গ্যারান্টি",
        help_text="Guarantee/warranty text"
    )
    
    # Contact information
    support_phone = models.CharField(
        max_length=40, 
        default="+8801XXXXXXXXX",
        help_text="Customer support phone number"
    )
    support_whatsapp = models.CharField(
        max_length=40, 
        blank=True, 
        default="",
        help_text="WhatsApp number for customer support"
    )
    
    # Trust and shipping
    trust_badges = models.JSONField(
        default=list,
        blank=True,
        help_text="Trust badges/icons. Format: [{'name': 'Badge Name', 'icon': 'icon-class', 'text': 'Badge text'}]"
    )
    shipping_notice = models.CharField(
        max_length=160, 
        default="ঢাকার ভিতরে 24-48 ঘন্টায় ডেলিভারি",
        help_text="Shipping time notice"
    )
    cta_text = models.CharField(
        max_length=60, 
        default="এখনই অর্ডার করুন",
        help_text="Call-to-action button text"
    )
    
    # Additional features for urgency/scarcity
    enable_countdown = models.BooleanField(default=False, help_text="Enable countdown timer")
    countdown_end_date = models.DateTimeField(null=True, blank=True, help_text="Countdown end date/time")
    countdown_text = models.CharField(
        max_length=100, 
        default="অফার শেষ হতে বাকি",
        blank=True,
        help_text="Text to show before countdown"
    )
    
    enable_stock_counter = models.BooleanField(default=False, help_text="Enable stock counter display")
    stock_counter_text = models.CharField(
        max_length=80, 
        default="স্টকে আছে মাত্র",
        blank=True,
        help_text="Text to show before stock count"
    )
    
    # Social proof settings
    enable_social_proof = models.BooleanField(default=True, help_text="Enable social proof notifications")
    social_proof_interval = models.PositiveIntegerField(
        default=8000, 
        help_text="Interval between social proof notifications (milliseconds)"
    )
    
    objects = SiteConfigManager()

    def save(self, *args, **kwargs):
        """Override save to ensure only one instance exists"""
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Prevent deletion of the singleton instance"""
        pass

    @classmethod
    def get_config(cls):
        """Class method to get the singleton instance"""
        return cls.objects.get_config()

    def __str__(self):
        return "Site Configuration"

    class Meta:
        verbose_name = "Site Configuration"
        verbose_name_plural = "Site Configuration"

# ---------- PriceHistory ----------
class PriceHistory(models.Model):
    variation = models.ForeignKey('ProductVariation', on_delete=models.CASCADE, related_name='price_entries')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    date_time = models.DateTimeField(default=timezone.now)
    notes = models.CharField(max_length=200, blank=True, null=True)  # Optional notes like "sale", "supplier change", etc.

    def __str__(self):
        return f"{self.variation.sku} - ৳{self.price} ({self.date_time.strftime('%Y-%m-%d %H:%M')})"

    class Meta:
        verbose_name = "Price History"
        verbose_name_plural = "Price Histories"
        ordering = ['-date_time']  # Latest first

# ---------- ProductVariation ----------
class ProductVariationManager(models.Manager):
    def get_by_natural_key(self, sku):
        return self.get(sku=sku)

class ProductVariation(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variations')
    name = models.CharField(max_length=500)  # e.g. "Red / Large"
    sku = models.CharField(max_length=500, unique=True)
    image = models.ImageField(
        upload_to='product_variations/',
        storage=PassthroughURLStorage(),
        max_length=600,
        blank=True,
        null=True
    )
    url = models.CharField(max_length=500, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    
    # Price crawling fields
    is_crawling_enabled = models.BooleanField(default=True, help_text="Enable automatic price crawling for this variation")
    last_crawled_at = models.DateTimeField(null=True, blank=True, help_text="Last time price was successfully crawled")
    crawl_error_count = models.PositiveIntegerField(default=0, help_text="Number of consecutive crawl errors")
    last_crawl_error = models.TextField(blank=True, null=True, help_text="Last crawl error message")

    objects = ProductVariationManager()

    def __str__(self):
        return f"{self.product.name} - {self.name}"

    @property
    def price(self):
        """Get the latest price from price history"""
        latest = self.price_entries.first()  # Already ordered by -date_time
        return latest.price if latest else 0

    def add_price(self, price, date_time=None, notes=None):
        """Add a new price to the history"""
        if date_time is None:
            date_time = timezone.now()
        
        PriceHistory.objects.create(
            variation=self,
            price=price,
            date_time=date_time,
            notes=notes
        )

    def update_crawl_success(self, price):
        """Update crawl tracking fields after successful crawl"""
        self.last_crawled_at = timezone.now()
        self.crawl_error_count = 0
        self.last_crawl_error = None
        self.save(update_fields=['last_crawled_at', 'crawl_error_count', 'last_crawl_error'])

    def update_crawl_error(self, error_message):
        """Update crawl tracking fields after error"""
        self.crawl_error_count += 1
        self.last_crawl_error = error_message[:500]  # Truncate if too long
        self.save(update_fields=['crawl_error_count', 'last_crawl_error'])

    def should_crawl(self):
        """Check if this variation should be crawled"""
        if not self.is_crawling_enabled or not self.url:
            return False
        
        # Don't crawl if too many consecutive errors
        if self.crawl_error_count >= 5:
            return False
            
        return True

    def crawl_status_display(self):
        """Display crawl status for admin"""
        if not self.url:
            return "No URL"
        if not self.is_crawling_enabled:
            return "Disabled"
        if self.crawl_error_count >= 5:
            return f"Failed ({self.crawl_error_count} errors)"
        if self.last_crawled_at:
            return f"Last crawled: {self.last_crawled_at.strftime('%Y-%m-%d %H:%M')}"
        return "Never crawled"

    def current_stock(self):
        entries = self.stockentry_set.aggregate(total=models.Sum('quantity'))['total'] or 0
        sales = self.retailsale_set.aggregate(total=models.Sum('quantity'))['total'] or 0
        return entries - sales

    def natural_key(self):
        return (self.sku,)
    natural_key.dependencies = []

# ---------- Supplier ----------
class SupplierManager(models.Manager):
    def get_by_natural_key(self, slug):
        return self.get(slug=slug)

class Supplier(models.Model):
    name = models.CharField(max_length=500)
    slug = models.CharField(max_length=500, unique=True, blank=True)  # ensure uniqueness
    contact_info = models.TextField(blank=True, null=True)

    objects = SupplierManager()

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
            # Handle duplicate slugs
            counter = 1
            original_slug = self.slug
            while Supplier.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def natural_key(self):
        return (self.slug,)

# ---------- StockEntry ----------
class StockEntry(models.Model):
    variation = models.ForeignKey(ProductVariation, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True)
    purchase_date = models.DateField(default=timezone.now)
    receipt_info = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.variation.name} - {self.quantity} @ {self.unit_price}"
    
    class Meta:
        verbose_name = "Stock Entry"
        verbose_name_plural = "Stock Entries"

# ---------- RetailSale ----------
class RetailSale(models.Model):
    variation = models.ForeignKey(ProductVariation, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    retail_price = models.DecimalField(max_digits=10, decimal_places=2)  # price at time of sale
    sale_date = models.DateField(default=timezone.now)

    def __str__(self):
        return f"{self.variation.name} - {self.quantity} @ {self.retail_price}"

# ---------- Customer ----------
class CustomerManager(models.Manager):
    def get_by_natural_key(self, phone):
        return self.get(phone=phone)

class Customer(models.Model):
    DISTRICT_CHOICES = [
        ('dhaka', 'ঢাকা'),
        ('chittagong', 'চট্টগ্রাম'),
        ('rajshahi', 'রাজশাহী'),
        ('khulna', 'খুলনা'),
        ('barisal', 'বরিশাল'),
        ('sylhet', 'সিলেট'),
        ('rangpur', 'রংপুর'),
        ('mymensingh', 'ময়মনসিংহ'),
        ('comilla', 'কুমিল্লা'),
        ('feni', 'ফেনী'),
        ('brahmanbaria', 'ব্রাহ্মণবাড়িয়া'),
        ('noakhali', 'নোয়াখালী'),
        ('chandpur', 'চাঁদপুর'),
        ('lakshmipur', 'লক্ষ্মীপুর'),
        ('coxsbazar', "কক্সবাজার"),
        ('rangamati', 'রাঙ্গামাটি'),
        ('bandarban', 'বান্দরবান'),
        ('khagrachhari', 'খাগড়াছড়ি'),
        # Add more districts as needed
    ]
    
    THANA_CHOICES = {
        'dhaka': [
            ('dhanmondi', 'ধানমন্ডি'),
            ('gulshan', 'গুলশান'),
            ('uttara', 'উত্তরা'),
            ('mohammadpur', 'মোহাম্মদপুর'),
            ('mirpur', 'মিরপুর'),
            ('ramna', 'রমনা'),
            ('tejgaon', 'তেজগাঁও'),
            ('pallabi', 'পল্লবী'),
            ('shah_ali', 'শাহ আলী'),
            ('kafrul', 'কাফরুল'),
        ],
        'chittagong': [
            ('kotwali', 'কোতোয়ালী'),
            ('panchlaish', 'পাঁচলাইশ'),
            ('double_mooring', 'ডাবল মুরিং'),
            ('pahartali', 'পাহাড়তলী'),
            ('bayazid', 'বায়েজিদ'),
            ('chandgaon', 'চাঁদগাঁও'),
        ],
        # Add more thanas for other districts
    }
    
    name = models.CharField(max_length=100)
    raw_address = models.TextField(verbose_name="Raw Address (from order)")
    formatted_address = models.TextField(blank=True, null=True, verbose_name="Formatted Clean Address")
    district = models.CharField(max_length=50, choices=DISTRICT_CHOICES, blank=True, null=True, verbose_name="জেলা")
    thana = models.CharField(max_length=50, blank=True, null=True, verbose_name="থানা")
    phone = models.CharField(max_length=20, unique=True, blank=True)  # make unique if you choose phone as natural key
    fraud_report_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    cancellation_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CustomerManager()

    def __str__(self):
        return f"{self.name} - {self.phone}"

    def natural_key(self):
        return (self.phone,)

    class Meta:
        verbose_name = "Customer"
        verbose_name_plural = "Customers"

# ---------- Order ----------
class Order(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='orders')
    variation = models.ForeignKey(ProductVariation, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    order_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    @property
    def total_amount(self):
        return self.variation.price * self.quantity

    def __str__(self):
        return f"Order #{self.id} - {self.customer.name} - {self.variation.product.name}"

    class Meta:
        verbose_name = "Order"
        verbose_name_plural = "Orders"
        ordering = ['-order_date']
