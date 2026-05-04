from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    RuleSetViewSet, RuleVersionViewSet, RuleClauseViewSet,
    evaluate_edition,
)

router = DefaultRouter()
router.register('rulesets', RuleSetViewSet)
router.register('rule-versions', RuleVersionViewSet)
router.register('rule-clauses', RuleClauseViewSet)

urlpatterns = [
    path('evaluate/<int:edition_id>/', evaluate_edition, name='evaluate_edition'),
] + router.urls
