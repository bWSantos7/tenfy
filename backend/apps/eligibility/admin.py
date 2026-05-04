from django.contrib import admin
from .models import RuleSet, RuleVersion, RuleClause, TournamentRuleBinding


@admin.register(RuleSet)
class RuleSetAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'scope')
    list_filter = ('organization',)
    search_fields = ('name', 'scope')


class RuleClauseInline(admin.TabularInline):
    model = RuleClause
    extra = 0


@admin.register(RuleVersion)
class RuleVersionAdmin(admin.ModelAdmin):
    list_display = ('ruleset', 'version', 'status', 'effective_from', 'effective_to')
    list_filter = ('status', 'ruleset')
    inlines = [RuleClauseInline]


@admin.register(RuleClause)
class RuleClauseAdmin(admin.ModelAdmin):
    list_display = ('rule_version', 'clause_type', 'category_code')
    list_filter = ('clause_type',)


@admin.register(TournamentRuleBinding)
class TournamentRuleBindingAdmin(admin.ModelAdmin):
    list_display = ('edition', 'ruleset', 'pinned_version', 'is_primary', 'binding_reason')
    list_filter = ('is_primary', 'ruleset')
    search_fields = ('edition__title', 'ruleset__name', 'binding_reason')
    autocomplete_fields = ('ruleset',)
