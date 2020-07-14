from allauth.account.adapter import DefaultAccountAdapter


class AnimeSukiAccountAdapter(DefaultAccountAdapter):

    def is_open_for_signup(self, request):
        """For the time being, user registration is closed"""
        return False
