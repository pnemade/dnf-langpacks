from dnfpluginscore import _

import dnf
import dnf.cli

conditional_pkgs = {}

class _lazy_import_langtable:

    def __init__(self):
        self.mod = None

    def __getattr__(self, name):
        if self.mod is None:
            import langtable
            self.mod = langtable
        return getattr(self.mod, name)

langtable = _lazy_import_langtable()

class Langpacks(dnf.Plugin):
    """DNF plugin supplying the 'langpacks langavailable' command."""

    name = 'langpacks'
    def __init__(self, base, cli):
        """Initialize the plugin instance."""
        super(Langpacks, self).__init__(base, cli)
        if cli is not None:
            cli.register_command(LangavailableCommand)
        cli.logger.debug("initialized Langpacks plugin")

