from django import template
register = template.Library()

BRANCH_COLORS = {
    100: "#758ECD", 101: "#3D405B", 102: "#FFD166", 103: "#87BBA2", 104: "#F3A183",
    105: "#AFB6E2", 106: "#6ECEDA", 107: "#FFD6BA", 108: "#CBD18F", 109: "#B892FF",
    110: "#7E9B7B", 111: "#FFD5E5", 112: "#B7E4C7", 113: "#FFA69E"
}

@register.filter
def branch_color(code):
    try:
        return BRANCH_COLORS.get(int(code), "#E0E0E0")
    except:
        return BRANCH_COLORS.get(str(code), "#E0E0E0")