objects=-Wall -Werror=all -Wextra

CFLAGS:=$(filter-out $(objects),$(CFLAGS))
CXXFLAGS:=$(filter-out $(objects),$(CXXFLAGS))
