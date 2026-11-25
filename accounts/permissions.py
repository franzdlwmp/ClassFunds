from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    required_role = None

    def test_func(self):
        return self.request.user.role == self.required_role


class AdminRequiredMixin(RoleRequiredMixin):
    required_role = "admin"


class TreasurerRequiredMixin(RoleRequiredMixin):
    required_role = "treasurer"