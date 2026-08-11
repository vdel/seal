# How every Tilt resource seal declares on a project's behalf is named.
#
# These sit in the same flat namespace as the project's own resources, so
# they say whose they are: `seal_` marks them, and the name is coined
# rather than borrowed, so nothing a project would plausibly call a resource
# of its own starts that way.
#
# After the marker comes the purpose, then the service it belongs to:
#
#     seal_<purpose>[_<service_name>]
#
# Purpose first, so everything doing the same job sorts together whatever
# services a project has (`seal_tests_*`, `seal_reset_*`) -- and a
# purpose names what the resource is *for*, never the tool it happens to use
# to do it. The service is omitted for the one resource there is only ever
# one of per project.
#
# Underscores throughout, including inside the service name: these are
# local_resources, not Kubernetes objects, so DNS-1123's ban on underscores
# (which is why a project's own resources are hyphenated) doesn't apply, and
# one separator makes the whole name read as a single token.
SEAL_RESOURCE_PREFIX = 'seal_'


def seal_resource_name(purpose, service_name=None):
    name = SEAL_RESOURCE_PREFIX + purpose
    if service_name != None:
        name += '_' + service_name.replace('-', '_')
    return name
