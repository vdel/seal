# Convenience wrappers around examples/angular-django, the one project in
# this repo. A different/second project would want its own equivalent
# targets pointed at its own directory.

up:
	cd examples/angular-django && uvx --from ../../python seal up

down:
	cd examples/angular-django && tilt down
