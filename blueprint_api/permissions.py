from rest_framework import permissions

class ReadOnlyOrAuthenticated(permissions.BasePermission):
    """
    Allow anyone to GET, but restrict other methods to authenticated users.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_authenticated
