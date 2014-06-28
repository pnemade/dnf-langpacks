from dnfpluginscore import _

import dnf
import dnf.cli
import dnf.yum.misc
import os
import sys


class _LazyImportLangtable(object):
    """ load lazily langtable module """
    def __init__(self):
        self.mod = None

    def __getattr__(self, name):
        if self.mod is None:
            import langtable
            self.mod = langtable
        return getattr(self.mod, name)

langtable = _LazyImportLangtable()


class CompsParser(object):
    def __init__(self):
        self.__cached_c_element_tree = None

    def _c_element_tree_import(self):
        """ Importing xElementTree all the time, when we often don't need it, is a
            huge timesink. This makes python -c 'import yum' suck. So we hide it
            behind this function. And have accessors. """

        if self.__cached_c_element_tree is None:
            from xml.etree import cElementTree
            self.__cached_c_element_tree = cElementTree

    def c_elementtree_iterparse(self, filename):
        """ Lazily load/run: cElementTree.iterparse """
        self._c_element_tree_import()
        return self.__cached_c_element_tree.iterparse(filename)

    def iterparse(self, filename):
        try:
            for e in self.c_elementtree_iterparse(filename):
                yield e
        except SyntaxError as e:
            print >>sys.stderr, '%s: %s' % (filename, str(e))


class LangpackCommon(object):
    def __init__(self):
        self.conditional_pkgs = {}

    @classmethod
    def langcode_to_langname(cls, langcode):
        """ We need to get the language name for the given locale code  """
        return langtable.language_name(languageId=langcode,
                                    languageIdQuery="en").encode("UTF-8")

    @classmethod
    def langname_to_langcode(cls, langname):
        """ We need to get the locale code for the given language name """
        return langtable.languageId(languageName=langname)

    def setup_conditional_pkgs(self, repos):
        """ This takes ~0.2 seconds to init, so only do it if we need to
            This is called to check if cond pkg already setup """
        if not self.conditional_pkgs:
            self.my_postreposetup_hook(repos)

    def my_postreposetup_hook(self, repos):
        """ This takes ~0.2 seconds to init, so don't do it for non-transaction
            commands. This does mean we might end up downloading the groups
            file in postresolve, but meh. """

        for repo in repos:
            if not repo.enablegroups:
                continue
            if not repo.metadata:
                continue
            comps_fn = repo.metadata.comps_fn
            if comps_fn is None:
                continue

            if repo.md_only_cached:
                infile = dnf.yum.misc.calculate_repo_gen_dest(comps_fn, \
                                                             'groups.xml')
                if not os.path.exists(infile):
                    # root privileges are needed for comps decompression
                    continue
            else:
                infile = dnf.yum.misc.repo_gen_decompress(comps_fn, 'groups.xml')

            comparse = CompsParser()
            for event, elem in comparse.iterparse(infile):
                if elem.tag == "langpacks":
                    for child in elem.getchildren():
                        if child.tag != "match":
                            continue
                        name = child.get("name")
                        install = child.get("install")

                        if name not in self.conditional_pkgs:
                            self.conditional_pkgs[name] = []
                        self.conditional_pkgs[name].append(install)

    def read_available_langpacks(self, pkg_query_sack):
        """ Get the list of available language packages in the available repos """
        srchpkglist = []
        skip_pkg_list = ['devel', 'browser', 'debuginfo', 'music', 'overrides',
                     'Brazil', 'British', 'Farsi', 'LowSaxon', 'cs_CZ']
        langlist = []
        seen = set()
        res = []

        packages = pkg_query_sack.query().available()
        for basepkg in self.conditional_pkgs:
            conds = self.conditional_pkgs[basepkg]
            pkg_pat = conds[0]
            # Special case to skip tesseract packages
            if not (pkg_pat.startswith("tesseract-langpack-")):
                srchpkglist.append(pkg_pat[:-2])

        for srchpat in srchpkglist:
            srchpat = srchpat + "*"
            srch_pat_pkgs = packages.filter(name__glob=srchpat)
            for pkg in srch_pat_pkgs:
                # Note I see here pkg is returning unicode string and
                # all other code still uses str type strings.
                res.append(str(pkg.name))

        for srchpkg in srchpkglist:
            for pkgname in res:
                if pkgname not in seen:
                    if pkgname.startswith(srchpkg):
                        langsplit = pkgname.split('-')
                        # lname is available language pack
                        lname = langsplit[srchpkg.count('-')]
                        # Special case for parsing packages alphabet_sounds_*
                        if lname.startswith("alphabet_sounds_"):
                            lname = lname[16:]
                        seen.add(pkgname)

                        if lname not in langlist:
                            if lname not in skip_pkg_list:
                                langlist.append(lname)

        return (seen, langlist)

    def get_unique_language_names(self, alllanglist):
        """ Let's gather available languages list"""
        uniq_lang_list = []
        dup = 0
        processed = 0
        item = ""
        for item in alllanglist:
            if item.count('_') or len(item) < 4:
                processed = processed + 1
                langname = self.langcode_to_langname(item)

                if len(langname) < 1:
                    uniq_lang_list.append(langname)

                if langname not in uniq_lang_list:
                    uniq_lang_list.append(langname)
                else:
                    dup = dup + 1
            else:
                if item not in uniq_lang_list:
                    uniq_lang_list.append(item)
                else:
                    dup = dup + 1

        return sorted(uniq_lang_list)

class LangavailableCommand(dnf.cli.Command):
    """ Langpacks Langavailable plugin for DNF """

    aliases = ("langavailable",)
    summary = _('Search available langpack packages')
    usage = "[LANG...]"

    def configure(self, args):
        demands = self.cli.demands
        demands.resolving = True
        demands.root_user = False
        demands.sack_activation = True

    def run(self, args):
        self.base.fill_sack()
        langc = LangpackCommon()
        langc.setup_conditional_pkgs(self.base.repos.iter_enabled())
        (language_packs, ra_list) = langc.read_available_langpacks(self.base.sack)
        langlist = langc.get_unique_language_names(ra_list)

        if not args:
            print("Displaying all available language:-")
            for litem in langlist:
                lcname = langc.langname_to_langcode(litem)
                if lcname == "zh_Hans_CN":
                    lcname = "zh_CN"
                elif lcname == "zh_Hant_TW":
                    lcname = "zh_TW"
                print("{0} [{1}]".format(litem, lcname))
        else:
            for lang in args:
                if len(lang) > 3 and lang.find("_") == -1:
                    if lang.lower() in list(map(str.lower, langlist)):
                        print("{0} is available".format(lang))
                    else:
                        print("{0} is not available".format(lang))
                else:
                    if langc.langcode_to_langname(lang) in langlist:
                        print("{0} is available".format(lang))
                    else:
                        print("{0} is not available".format(lang))

        return 0, [""]


class Langpacks(dnf.Plugin):
    """DNF plugin supplying the 'langpacks langavailable' command."""

    name = 'langpacks'
    def __init__(self, base, cli):
        """Initialize the plugin instance."""
        super(Langpacks, self).__init__(base, cli)
        if cli is not None:
            cli.register_command(LangavailableCommand)
        cli.logger.debug("initialized Langpacks plugin")

