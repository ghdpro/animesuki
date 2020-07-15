"""AnimeSuki Core views"""

from django.views.generic import TemplateView


class FrontpageView(TemplateView):
    template_name = 'frontpage.html'
