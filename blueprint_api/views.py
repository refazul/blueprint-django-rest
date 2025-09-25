# views.py

from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.generics import RetrieveAPIView
from rest_framework.pagination import PageNumberPagination
from .serializers import *
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.utils import timezone
import json
from django.db.models import Q, Count
from rest_framework.views import APIView
from datetime import timedelta

class PriceAnalysisPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.prefetch_related('images').all()
    serializer_class = CategorySerializer
    lookup_field = 'slug'

class CategoryImageViewSet(viewsets.ModelViewSet):
    queryset = CategoryImage.objects.select_related('category').all()
    serializer_class = CategoryImageSerializer
    
    def get_queryset(self):
        queryset = CategoryImage.objects.select_related('category').all()
        category_slug = self.request.query_params.get('category', None)
        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)
        return queryset

class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.prefetch_related('variations', 'categories').all()
    serializer_class = ProductSerializer
    lookup_field = 'slug'
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductSerializer

class ProductVariationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ProductVariation.objects.select_related('product').all()
    serializer_class = ProductVariationSerializer
    lookup_field = 'sku'

class SupplierViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    lookup_field = 'slug'

class StockEntryViewSet(viewsets.ModelViewSet):
    queryset = StockEntry.objects.all()
    serializer_class = StockEntrySerializer

class RetailSaleViewSet(viewsets.ModelViewSet):
    queryset = RetailSale.objects.all()
    serializer_class = RetailSaleSerializer

class CategoryPageAPIView(APIView):
    def get(self, request, slug):
        try:
            category = Category.objects.prefetch_related('images').get(slug=slug)
        except Category.DoesNotExist:
            return Response({'error': 'Category not found'}, status=status.HTTP_404_NOT_FOUND)

        # Get descendant categories
        descendants = Category.objects.filter(
            Q(id=category.id) |
            Q(parent=category) |
            Q(parent__parent=category) |
            Q(parent__parent__parent=category)
        )
        
        # Get base products for this category and all subcategories
        products = Product.objects.filter(categories__in=descendants).prefetch_related(
            'variations', 'attributes__category_attribute', 'attributes__selected_choices'
        ).distinct()
        
        print(f"Base products count (including subcategories): {products.count()}")
        print(f"Descendant categories: {[cat.name for cat in descendants]}")
        print(f"Query params: {request.GET}")

        # Apply attribute-based filtering (using ALL descendant categories)
        filter_params = self.get_filter_params(request, descendants)  # Changed here
        print(f"Filter params: {filter_params}")
        
        if filter_params:
            products = self.apply_attribute_filters(products, filter_params)
            print(f"Filtered products count: {products.count()}")

        # Serialize the data
        category_data = CategoryPageSerializer(category).data
        subcategories_data = CategorySerializer(category.subcategories.all(), many=True).data
        products_data = CategoryPageProductSerializer(products, many=True).data

        # Get available filter options for ALL categories (including subcategories)
        base_products = Product.objects.filter(categories__in=descendants).prefetch_related(  # Changed here
            'variations', 'attributes__category_attribute', 'attributes__selected_choices'
        ).distinct()
        available_filters = self.get_available_filters(descendants, base_products)  # Changed here

        return Response({
            'category': category_data,
            'subcategories': subcategories_data,
            'products': products_data,
            'filters': available_filters,
            'applied_filters': filter_params,
            'total_products': products.count(),
            'debug': {
                'query_params': dict(request.GET),
                'filter_params': filter_params,
                'included_categories': [cat.name for cat in descendants]  # Changed debug info
            }
        })

    def get_filter_params(self, request, categories):  # Changed parameter
        """Extract filter parameters from URL query params"""
        filter_params = {}
        
        # Get all attributes for ALL categories (including subcategories)
        all_attributes = []
        for cat in categories:
            all_attributes.extend(cat.get_all_attributes())
        
        # Remove duplicates by slug
        unique_attributes = {}
        for attr in all_attributes:
            unique_attributes[attr.slug] = attr
        category_attributes = list(unique_attributes.values())
        
        print(f"All category attributes: {[attr.name + ' -> ' + attr.slug for attr in category_attributes]}")
        
        for attr in category_attributes:
            # Convert attribute name to URL-friendly parameter
            param_name = self.attr_name_to_param(attr.name)
            print(f"Checking param: {param_name} for attribute: {attr.name}")
            
            # Check case-insensitive parameter names
            param_value = None
            for key in request.GET.keys():
                if key.lower() == param_name.lower():
                    param_value = request.GET.get(key)
                    break
                    
            if param_value:
                # Split comma-separated values for OR logic
                values = [v.strip() for v in param_value.split(',')]
                filter_params[attr.slug] = values
                print(f"Found filter: {attr.slug} = {values}")
                
        return filter_params

    def attr_name_to_param(self, attr_name):
        """Convert attribute name to URL parameter format"""
        # "Processor" -> "processor", "Storage Capacity" -> "storage_capacity"
        return attr_name.lower().replace(' ', '_').replace('-', '_')

    def apply_attribute_filters(self, products, filter_params):
        """Apply attribute-based filters to products queryset"""
        print(f"Starting with {products.count()} products")
        print(f"Products have these attributes:")
        
        # Debug: Show what attributes exist on products
        for product in products[:5]:  # Just check first 5 products
            product_attrs = product.attributes.all()
            # Get first choice for display (since we now have multiple choices)
            attr_info = []
            for attr in product_attrs:
                choices = attr.selected_choices.all()
                if choices:
                    first_choice = choices[0].value
                    if len(choices) > 1:
                        first_choice += f" (+{len(choices)-1} more)"
                    attr_info.append((attr.category_attribute.name, first_choice))
            print(f"  {product.name}: {attr_info}")
        
        for attr_slug, choice_values in filter_params.items():
            print(f"Applying filter: {attr_slug} = {choice_values}")
            
            # Ensure choice_values is a list
            if not isinstance(choice_values, list):
                choice_values = [choice_values]
            
            try:
                # Get the attribute
                category_attr = CategoryAttribute.objects.get(slug=attr_slug)
                print(f"Found category attribute: {category_attr}")
                
                # Debug: Check if any products have this attribute
                products_with_attr = products.filter(attributes__category_attribute=category_attr)
                print(f"Products with attribute '{category_attr.name}': {products_with_attr.count()}")
                
                # Find all matching choices (OR logic)
                matching_choices = []
                for choice_value in choice_values:
                    choice = None
                    try:
                        choice = CategoryAttributeChoice.objects.get(
                            attribute=category_attr,
                            value__iexact=choice_value
                        )
                        matching_choices.append(choice)
                        print(f"Found exact choice: {choice}")
                    except CategoryAttributeChoice.DoesNotExist:
                        print(f"Exact choice not found: {choice_value}")
                        # Try partial match (contains)
                        choices = CategoryAttributeChoice.objects.filter(
                            attribute=category_attr,
                            value__icontains=choice_value
                        )
                        if choices.exists():
                            matching_choices.extend(list(choices))
                            print(f"Found partial choices: {list(choices)}")
                        else:
                            print(f"No partial matches for: {choice_value}")
                            # Show available choices for debugging
                            all_choices = CategoryAttributeChoice.objects.filter(attribute=category_attr)
                            print(f"Available choices: {[c.value for c in all_choices]}")
        
                if matching_choices:
                    # Debug: Check products before filtering
                    print(f"Products before choice filter: {products.count()}")
                    
                    # Filter products that have ANY of these attribute choices (OR logic)
                    products = products.filter(
                        attributes__category_attribute=category_attr,
                        attributes__selected_choices__in=matching_choices
                    )
                    print(f"Products after OR filter: {products.count()}")
                    
                    # Debug: Show which products matched
                    for product in products[:3]:  # Show first 3 matches
                        matching_attr = product.attributes.filter(
                            category_attribute=category_attr,
                            selected_choices__in=matching_choices
                        ).first()
                        if matching_attr:
                            first_choice = matching_attr.selected_choices.filter(id__in=[c.id for c in matching_choices]).first()
                            if first_choice:
                                print(f"  Matched product: {product.name} -> {first_choice.value}")
                
                else:
                    print(f"No matching choices found for: {choice_values}")
                    # Return empty queryset if no choices match
                    return products.none()
                    
            except CategoryAttribute.DoesNotExist:
                print(f"CategoryAttribute not found: {attr_slug}")
                # Return empty queryset if attribute doesn't exist
                return products.none()
            
        return products.distinct()

    def get_available_filters(self, categories, products):  # Changed parameter
        """Get all available filter options for all categories"""
        filters = []
        
        # Get all attributes for ALL categories (including subcategories)
        all_attributes = []
        for cat in categories:
            all_attributes.extend(cat.get_all_attributes())
        
        # Remove duplicates by slug
        unique_attributes = {}
        for attr in all_attributes:
            unique_attributes[attr.slug] = attr
        category_attributes = list(unique_attributes.values())
        
        for attr in category_attributes:
            param_name = self.attr_name_to_param(attr.name)
            
            # Get all choices that are actually used by products
            used_choices = CategoryAttributeChoice.objects.filter(
                attribute=attr,
                #productattribute__product__in=products  # Uncommented this line
            ).distinct().order_by('display_order', 'value')

            if used_choices.exists():  # Only include attributes that have choices
                filters.append({
                    'name': attr.name,
                    'slug': attr.slug,
                    'choices': [
                        {
                            'value': choice.value,
                            'slug': choice.slug,
                            'param_value': choice.value
                        }
                        for choice in used_choices
                    ]
                })

        return filters

@api_view(['POST'])
@permission_classes([AllowAny])
def create_order(request):
    serializer = OrderCreateSerializer(data=request.data)
    if serializer.is_valid():
        order = serializer.save()
        order_serializer = OrderSerializer(order)
        return Response(order_serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    
    def get_serializer_class(self):
        if self.action == 'create':
            return OrderCreateSerializer
        return OrderSerializer

@csrf_exempt
@require_http_methods(["POST"])
def update_price(request):
    try:
        data = json.loads(request.body)
        sku = data.get('sku')
        price = data.get('price')
        notes = data.get('notes', '')  # Optional notes
        
        if not sku or price is None:
            return JsonResponse({'error': 'sku and price are required'}, status=400)
        
        try:
            variation = ProductVariation.objects.get(sku=sku)
        except ProductVariation.DoesNotExist:
            return JsonResponse({'error': 'Product variation not found'}, status=404)
        
        # Add new price to history
        variation.add_price(price, notes=notes)
        
        return JsonResponse({
            'success': True,
            'sku': sku,
            'new_price': float(price),
            'notes': notes,
            'updated_at': timezone.now().isoformat()
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

class NavigationAPIView(APIView):
    """API endpoint that renders navigation with recursive items structure"""
    
    def get(self, request):
        def build_category_items(category, max_depth=5, current_depth=0):
            """Recursively build category items"""
            result = {
                'name': category.name,
                'href': f'/category/{category.slug}/',
                'slug': category.slug
            }
            
            # Get direct children
            if current_depth < max_depth:
                children = category.subcategories.all().order_by('name')
                if children:
                    result['items'] = []
                    for child in children:
                        child_item = build_category_items(child, max_depth, current_depth + 1)
                        result['items'].append(child_item)
            
            return result
        
        # Get root categories (categories with no parent)
        root_categories = Category.objects.filter(parent=None).order_by('name')
        
        categories = []
        for root_cat in root_categories:
            category_data = build_category_items(root_cat)
            categories.append(category_data)
        
        return Response({
            'categories': categories
        })

# ===============================================
# PRICE ANALYSIS API VIEWS
# ===============================================

class PriceAnalysisAPIView(APIView):
    """
    API endpoint for comprehensive price analysis
    """
    permission_classes = [AllowAny]
    pagination_class = PriceAnalysisPagination

    def get(self, request):
        """Get price analysis based on query parameters"""
        days_back = int(request.query_params.get('days_back', 30))
        min_change_percent = float(request.query_params.get('min_change_percent', 1.0))
        limit = int(request.query_params.get('limit', 50))
        analysis_type = request.query_params.get('analysis_type', 'all_changes')

        # Validate parameters
        request_serializer = PriceAnalysisRequestSerializer(data={
            'days_back': days_back,
            'min_change_percent': min_change_percent,
            'limit': limit,
            'analysis_type': analysis_type
        })
        
        if not request_serializer.is_valid():
            return Response(request_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Perform analysis
        analysis_data = self._perform_price_analysis(days_back, min_change_percent, limit, analysis_type)
        
        return Response(analysis_data)

    def _perform_price_analysis(self, days_back, min_change_percent, limit, analysis_type):
        """Perform the actual price analysis"""
        cutoff_date = timezone.now() - timedelta(days=days_back)
        
        # Get variations with multiple price entries for analysis
        variations_with_multiple = ProductVariation.objects.annotate(
            price_history_count=Count('price_entries')
        ).filter(price_history_count__gt=1)

        if analysis_type in ['all_changes', 'drops_only', 'increases_only']:
            price_changes = self._analyze_price_changes(
                variations_with_multiple, cutoff_date, min_change_percent, limit, analysis_type
            )
            
            # Calculate summary stats
            drops = [p for p in price_changes if p['change_type'] == 'DECREASE']
            increases = [p for p in price_changes if p['change_type'] == 'INCREASE']
            
            return {
                'summary': {
                    'total_changes': len(price_changes),
                    'price_drops': len(drops),
                    'price_increases': len(increases),
                    'days_analyzed': days_back,
                    'min_change_percent': min_change_percent
                },
                'price_changes': price_changes
            }

        elif analysis_type == 'volatile_only':
            volatile_prices = self._analyze_volatile_prices(variations_with_multiple, limit)
            return {
                'summary': {
                    'total_volatile_products': len(volatile_prices),
                    'days_analyzed': days_back
                },
                'volatile_prices': volatile_prices
            }

        return {'summary': {}, 'results': []}

    def _analyze_price_changes(self, variations, cutoff_date, min_change_percent, limit, analysis_type):
        """Analyze price changes for variations"""
        price_changes = []
        
        for variation in variations:
            recent_entries = list(variation.price_entries.filter(
                date_time__gte=cutoff_date
            ).order_by('-date_time'))
            
            if len(recent_entries) >= 2:
                latest_price = float(recent_entries[0].price)
                previous_price = float(recent_entries[1].price)
                
                if previous_price != latest_price and previous_price > 0:
                    change_percent = ((latest_price - previous_price) / previous_price) * 100
                    change_amount = latest_price - previous_price
                    change_type = "INCREASE" if change_percent > 0 else "DECREASE"
                    
                    if abs(change_percent) >= min_change_percent:
                        if (analysis_type == 'all_changes' or
                            (analysis_type == 'drops_only' and change_type == 'DECREASE') or
                            (analysis_type == 'increases_only' and change_type == 'INCREASE')):
                            
                            price_changes.append({
                                'sku': variation.sku,
                                'product_name': variation.product.name,
                                'variation_name': variation.name,
                                'current_price': latest_price,
                                'previous_price': previous_price,
                                'change_amount': change_amount,
                                'change_percent': change_percent,
                                'change_type': change_type,
                                'last_change_date': recent_entries[0].date_time,
                                'total_price_entries': variation.price_entries.count()
                            })
        
        price_changes.sort(key=lambda x: abs(x['change_percent']), reverse=True)
        return price_changes[:limit]

    def _analyze_volatile_prices(self, variations, limit):
        """Analyze volatile prices"""
        volatile_products = []
        
        for variation in variations.filter(price_history_count__gte=3):
            price_entries = list(variation.price_entries.order_by('date_time'))
            prices = [float(p.price) for p in price_entries]
            
            if len(prices) >= 3:
                min_price = min(prices)
                max_price = max(prices)
                volatility_percent = ((max_price - min_price) / min_price * 100) if min_price > 0 else 0
                
                if volatility_percent > 0:
                    volatile_products.append({
                        'sku': variation.sku,
                        'product_name': variation.product.name,
                        'variation_name': variation.name,
                        'current_price': float(variation.price),
                        'min_price': min_price,
                        'max_price': max_price,
                        'volatility_percent': volatility_percent,
                        'total_price_entries': len(prices)
                    })
        
        volatile_products.sort(key=lambda x: x['volatility_percent'], reverse=True)
        return volatile_products[:limit]


@api_view(['GET'])
@permission_classes([AllowAny])
def price_drops_api(request):
    """API endpoint specifically for price drops with pagination"""
    days_back = int(request.query_params.get('days_back', 30))
    min_drop_percent = float(request.query_params.get('min_drop_percent', 5.0))
    page_size = int(request.query_params.get('page_size', 20))
    page = int(request.query_params.get('page', 1))
    
    analysis_view = PriceAnalysisAPIView()
    analysis_data = analysis_view._perform_price_analysis(
        days_back, min_drop_percent, page_size * 5, 'drops_only'  # Get more data for pagination
    )
    
    # Filter only drops and format
    drops_data = []
    for change in analysis_data.get('price_changes', []):
        if change['change_type'] == 'DECREASE':
            drops_data.append({
                'sku': change['sku'],
                'product_name': change['product_name'],
                'variation_name': change['variation_name'],
                'current_price': change['current_price'],
                'previous_price': change['previous_price'],
                'drop_amount': abs(change['change_amount']),
                'drop_percent': abs(change['change_percent']),
                'last_change_date': change['last_change_date']
            })
    
    # Manual pagination
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_drops = drops_data[start_idx:end_idx]
    
    total_pages = (len(drops_data) + page_size - 1) // page_size
    
    return Response({
        'summary': {
            'total_drops': len(drops_data),
            'days_analyzed': days_back,
            'min_drop_percent': min_drop_percent
        },
        'pagination': {
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'total_results': len(drops_data),
            'has_next': page < total_pages,
            'has_previous': page > 1
        },
        'price_drops': paginated_drops
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def price_increases_api(request):
    """API endpoint specifically for price increases with pagination"""
    days_back = int(request.query_params.get('days_back', 30))
    min_increase_percent = float(request.query_params.get('min_increase_percent', 5.0))
    page_size = int(request.query_params.get('page_size', 20))
    page = int(request.query_params.get('page', 1))
    
    analysis_view = PriceAnalysisAPIView()
    analysis_data = analysis_view._perform_price_analysis(
        days_back, min_increase_percent, page_size * 5, 'increases_only'
    )
    
    # Filter only increases and format
    increases_data = []
    for change in analysis_data.get('price_changes', []):
        if change['change_type'] == 'INCREASE':
            increases_data.append({
                'sku': change['sku'],
                'product_name': change['product_name'],
                'variation_name': change['variation_name'],
                'current_price': change['current_price'],
                'previous_price': change['previous_price'],
                'increase_amount': change['change_amount'],
                'increase_percent': change['change_percent'],
                'last_change_date': change['last_change_date']
            })
    
    # Manual pagination
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_increases = increases_data[start_idx:end_idx]
    
    total_pages = (len(increases_data) + page_size - 1) // page_size
    
    return Response({
        'summary': {
            'total_increases': len(increases_data),
            'days_analyzed': days_back,
            'min_increase_percent': min_increase_percent
        },
        'pagination': {
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'total_results': len(increases_data),
            'has_next': page < total_pages,
            'has_previous': page > 1
        },
        'price_increases': paginated_increases
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def volatile_prices_api(request):
    """API endpoint for products with volatile price history"""
    limit = int(request.query_params.get('limit', 50))
    
    analysis_view = PriceAnalysisAPIView()
    analysis_data = analysis_view._perform_price_analysis(
        30, 0, limit, 'volatile_only'
    )
    
    return Response(analysis_data)


class SiteConfigAPIView(APIView):
    """
    API endpoint to get site configuration settings for landing pages
    Since SiteConfig is a singleton, we always return the first (and only) instance
    """
    permission_classes = [AllowAny]
    
    def get(self, request):
        try:
            from .models import SiteConfig
            config = SiteConfig.objects.first()
            if not config:
                # Create default config if none exists
                config = SiteConfig.objects.create()
            
            serializer = SiteConfigSerializer(config)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {'error': 'Unable to fetch site configuration'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
