"""
Context Processors untuk Port Gate TOS.
Menyediakan informasi peran pengguna (Admin vs Operator) ke semua template.
"""

from .mixins import is_admin_user, is_operator_user, get_user_role


def user_role_context(request):
    """
    Menyediakan flag peran global untuk kemudahan rendering template UI:
    - is_admin_role: True jika user adalah Administrator
    - is_operator_role: True jika user adalah Operator / non-Admin
    - user_role: string label peran ('Admin', 'Operator', 'Supervisor', 'Manager', 'Anonymous')
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {
            'is_admin_role': False,
            'is_operator_role': False,
            'user_role': 'Anonymous',
        }

    admin_flag = is_admin_user(request.user)
    return {
        'is_admin_role': admin_flag,
        'is_operator_role': not admin_flag,
        'user_role': get_user_role(request.user),
    }
