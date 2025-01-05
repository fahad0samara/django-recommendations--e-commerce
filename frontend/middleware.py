from .models import Cart

class CartMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Try to get cart from session
        cart_id = request.session.get('cart_id')
        
        if request.user.is_authenticated:
            # If user is logged in, get or create their cart
            cart, created = Cart.objects.get_or_create(user=request.user)
            request.session['cart_id'] = cart.id
            request.cart = cart
        elif cart_id:
            # If there's a cart in session, try to get it
            try:
                cart = Cart.objects.get(id=cart_id)
                request.cart = cart
            except Cart.DoesNotExist:
                cart = Cart.objects.create()
                request.session['cart_id'] = cart.id
                request.cart = cart
        else:
            # Create a new cart
            cart = Cart.objects.create()
            request.session['cart_id'] = cart.id
            request.cart = cart

        response = self.get_response(request)
        return response
