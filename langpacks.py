# -*- coding: utf-8 -*-
#
# Conditional language support packages, via a dnf plugin
#
# Copyright © 2014 Red Hat, Inc.
#
# Authors: Parag Nemade <pnemade@redhat.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

from dnfpluginscore import _, logger

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
            for elem in self.c_elementtree_iterparse(filename):
                yield elem
        except SyntaxError as elem:
            print >>sys.stderr, '%s: %s' % (filename, str(elem))


class LangpackCommon(object):
    def __init__(self):
        self.conditional_pkgs = {}
        self.langinstalled = []
        self.conffile = '/var/lib/yum/plugins/langpacks/installed_langpacks'

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
            for tp in comparse.iterparse(infile):
                elem = tp[1]
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
        """ Common function for getting the list of languages in the
            available repos """
        srchpkglist = []
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

        return (res, srchpkglist)

    def read_available_langpacks_pkgs(self, pkg_query_sack):
        """ Get the names of language packages """
        langpkgs = set()

        (res, srchpkglist) = self.read_available_langpacks(pkg_query_sack)

        for srchpkg in srchpkglist:
            for pkgname in res:
                if pkgname not in langpkgs:
                    if pkgname.startswith(srchpkg):
                        langsplit = pkgname.split('-')
                        # lname is available language pack
                        lname = langsplit[srchpkg.count('-')]
                        # Special case for parsing packages alphabet_sounds_*
                        if lname.startswith("alphabet_sounds_"):
                            lname = lname[16:]
                        langpkgs.add(pkgname)

        return langpkgs

    def read_available_languages_list(self, pkg_query_sack):
        """ Get the available languages list """
        skip_pkg_list = ['devel', 'browser', 'debuginfo', 'music', 'overrides',
                     'Brazil', 'British', 'Farsi', 'LowSaxon', 'cs_CZ']
        lang_list = []
        langpkgs = set()

        (res, srchpkglist) = self.read_available_langpacks(pkg_query_sack)

        for srchpkg in srchpkglist:
            for pkgname in res:
                if pkgname not in langpkgs:
                    if pkgname.startswith(srchpkg):
                        langsplit = pkgname.split('-')
                        # lname is available language pack
                        lname = langsplit[srchpkg.count('-')]
                        # Special case for parsing packages alphabet_sounds_*
                        if lname.startswith("alphabet_sounds_"):
                            lname = lname[16:]
                        langpkgs.add(pkgname)

                        if lname not in lang_list:
                            if lname not in skip_pkg_list:
                                lang_list.append(lname)

        return lang_list

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

    def get_matches_from_repo(self, langpack_pkgs, lang):
        """ Get the package matches for a given language """
        avl_langpack_pkgs = []
        #Check if lang is empty, case like input mara, marat
        if len(lang) == 0:
            return avl_langpack_pkgs
        lname = self.langcode_to_langname(lang)
        lang = "-" + lang
        for pkgs in langpack_pkgs:
            if len(lang) < 5 and lang.find("_") == -1:
                if pkgs.find(lang, len(pkgs)-len(lang), len(pkgs)) > 0:
                    avl_langpack_pkgs.append(pkgs)
                if lname:
                    if pkgs.find(lname, len(pkgs)-len(lname), len(pkgs)) > 0:
                        avl_langpack_pkgs.append(pkgs)
            if len(lang) > 4 and lang.find("_") != -1:
                mainlang = lang[0:lang.find("_")]
                if pkgs.find(lang, len(pkgs)-len(lang), len(pkgs)) > 0:
                    avl_langpack_pkgs.append(pkgs)
                # if input pt_BR then show for pt and pt_BR
                # if input zh_CN then show for zh and zh_CN
                elif pkgs.find(mainlang, len(pkgs)-len(mainlang), len(pkgs)) > 0:
                    avl_langpack_pkgs.append(pkgs)

                if lname:
                    if pkgs.find(lname, len(pkgs)-len(lname), len(pkgs)) > 0:
                        avl_langpack_pkgs.append(pkgs)

        return sorted(avl_langpack_pkgs)

    def read_installed_langpacks(self):
        """ Read the installed langpacks file """
        if not self.conffile:
            return []
        ret = []
        try:
            conf_fp = open(self.conffile, "r")
            llist = conf_fp.readlines()
            conf_fp.close()
        except (IOError, OSError) as fperror:
            print >>sys.stderr, '%s' % (str(fperror))
            return []
        for item in llist:
            item = item.strip()
            ret.append(item)
        return ret

    def write_installed_langpacks(self, instlanglist):
        """ Write the installed langpacks file """
        if not self.conffile:
            return
        conffile_dir = os.path.dirname(self.conffile)
        if not os.path.exists(conffile_dir):
            try:
                os.makedirs(conffile_dir, 0755)
            except (IOError, OSError) as fperror:
                print >>sys.stderr, '%s' % (str(fperror))
                return
        try:
            tmp = open(self.conffile + ".tmp", "w+")
            for line in instlanglist:
                tmp.write(line + "\n")
            tmp.close()
            os.rename(self.conffile + ".tmp", self.conffile)
        except (IOError, OSError) as fperror:
            print >>sys.stderr, '%s' % (str(fperror))
            return

    def add_langpack_to_installed_list(self, langs):
        """ Add newly installed langs to the langpacks file """
        modified = 0
        readinstlanglist = self.read_installed_langpacks()
        for lang in langs:
            if lang not in readinstlanglist:
                readinstlanglist.append(lang)
                modified = 1
        if modified:
            self.write_installed_langpacks(readinstlanglist)

    @classmethod
    def get_matches(cls, availpkg, llist):
        ret = []
        for match in llist:
            try:
                p = availpkg.filter(provides=match)
                if p[0].name:
                    ret.append(p[0].name)
            except:
                pass
        return ret

    def add_matches_from_ts(self, lang, base):
        pkgmatches = []
        ipkgs = []
        pkgstoinstall = []
        allpkg = base.sack.query()
        instpkg = allpkg.installed()
        availpkg = allpkg.available()
        availpkg = availpkg.latest()
        for pkg in instpkg:
            ipkgs.append(pkg.name)

        for basepkg in self.conditional_pkgs:
            if basepkg in ipkgs:
                conds = self.conditional_pkgs[basepkg]
                patterns = [x % (lang,) for x in conds]
                shortlang = lang.split('_')[0]
                if shortlang != lang:
                    patterns = patterns + [x % (shortlang,) for x in conds]
                for p in patterns:
                    if p not in pkgmatches:
                        # just pattern matched pkgs irrespective of its existence
                        pkgmatches.append(p)

        # Available in repo pattern matched pkgs
        pkgs = self.get_matches(availpkg, pkgmatches)
        # we want to make sure pkgs return only if
        # those pkgs are available to be installed
        for pk in pkgs:
            if pk not in ipkgs:
                pkgstoinstall.append(pk)

        return pkgstoinstall

class LangavailableCommand(dnf.cli.Command):
    """ Langpacks Langavailable plugin for DNF """

    aliases = ("langavailable",)
    summary = _('Search available langpack packages')
    usage = "[LANG...]"

    def configure(self, args):
        demands = self.cli.demands
        demands.resolving = False
        demands.root_user = False
        demands.sack_activation = True

    def run(self, args):
        self.base.fill_sack()
        langc = LangpackCommon()
        langc.setup_conditional_pkgs(self.base.repos.iter_enabled())
        langavail_list = langc.read_available_languages_list(self.base.sack)
        lang_list = langc.get_unique_language_names(langavail_list)

        if not args:
            print("Displaying all available language:-")
            for litem in lang_list:
                lcname = langc.langname_to_langcode(litem)
                if lcname == "zh_Hans_CN":
                    lcname = "zh_CN"
                elif lcname == "zh_Hant_TW":
                    lcname = "zh_TW"
                print("{0} [{1}]".format(litem, lcname))
        else:
            for lang in args:
                if len(lang) > 3 and lang.find("_") == -1:
                    if lang.lower() in list(map(str.lower, lang_list)):
                        print("{0} is available".format(lang))
                    else:
                        print("{0} is not available".format(lang))
                else:
                    if langc.langcode_to_langname(lang) in lang_list:
                        print("{0} is available".format(lang))
                    else:
                        print("{0} is not available".format(lang))

        return 0, [""]

class LanginfoCommand(dnf.cli.Command):
    """ Langpacks Langinfo plugin for DNF """

    aliases = ("langinfo",)
    summary = _('Show langpack packages for a given language')
    usage = "[LANG...]"

    def configure(self, args):
        demands = self.cli.demands
        demands.resolving = False
        demands.root_user = False
        demands.sack_activation = True

    def run(self, args):
        self.base.fill_sack()
        whitelisted_locales = ['en_AU', 'en_CA', 'en_GB', 'pt_BR', \
                                                    'pt_PT', 'zh_CN', 'zh_TW']

        langc = LangpackCommon()
        langc.setup_conditional_pkgs(self.base.repos.iter_enabled())
        avail_langpack_pkgs = langc.read_available_langpacks_pkgs(self.base.sack)

        for lang in args:
            print("Language-Id={0}".format(lang))
            if len(lang) == 1:
                print("Not a valid input")
                return 0, [""]
            # Case to handle input like zh_CN, pt_BR
            elif lang in whitelisted_locales and len(lang) > 3 and \
                                                            lang.find("_") != -1:
                list_pkgs = langc.get_matches_from_repo(avail_langpack_pkgs, lang)
            # Case for full language name input like Japanese
            elif len(lang) > 3 and lang.find("_") == -1:
                list_pkgs = langc.get_matches_from_repo(avail_langpack_pkgs,\
                                                 langc.langname_to_langcode(lang))
            # General case to handle input like ja, ru, fr, it
            else:
                if lang.find("_") == -1:
                    list_pkgs = langc.get_matches_from_repo(avail_langpack_pkgs,\
                                                                            lang)
                # Case to not process mr_IN or mai_IN locales
                else:
                    list_pkgs = []
            for pkg in list_pkgs:
                print("  " + pkg)
            if len(list_pkgs) == 0:
                print("No langpacks to show for languages: {0}".format(lang))
        return 0, [""]

class LanglistCommand(dnf.cli.Command):
    """ Langpacks Langlist plugin for DNF """

    aliases = ("langlist",)
    summary = _('Show installed languages')
    usage = "[LANG...]"

    def configure(self, args):
        demands = self.cli.demands
        demands.resolving = False
        demands.root_user = False
        demands.sack_activation = True

    def run(self, args):
        langc = LangpackCommon()
        llist = langc.read_installed_langpacks()
        print("Installed languages:")
        for item in llist:
            if not item.startswith("#"):
                print("\t" + langc.langcode_to_langname(item))
        return 0, [""]

class LanginstallCommand(dnf.cli.Command):
    """ langinstall plugin for DNF """

    aliases = ("langinstall",)
    summary = _('Install the given packages')
    usage = "[PKG1...]"

    def configure(self, args):
        demands = self.cli.demands
        demands.resolving = False
        demands.root_user = True
        demands.sack_activation = True
        demands.available_repos = True

    def run(self, args):
        langc = LangpackCommon()
        langc.setup_conditional_pkgs(self.base.repos.iter_enabled())
        (language_packs, ra_list) = langc.read_available_langpacks(self.base.sack)
        all_pkgs = []

        for lang in args:
            if len(lang) > 3 and lang.find("_") == -1:
                pkgs = langc.add_matches_from_ts( \
                            langc.langname_to_langcode(lang), self.base)
                if pkgs and lang not in langc.langinstalled:
                    langc.langinstalled.append(langc.langname_to_langcode(lang))
                    for pk in pkgs:
                        all_pkgs.append(pk)
            else:
                pkgs = langc.add_matches_from_ts(lang, self.base)
                if pkgs and lang not in langc.langinstalled:
                    langc.langinstalled.append(lang)
                    for pk in pkgs:
                        all_pkgs.append(pk)

        for pkg in all_pkgs:
            try:
                self.base.install(pkg)
            except dnf.exceptions.MarkingError:
                msg = _("No matching package to install: '%s'") % pkg
                raise dnf.exceptions.Error(msg)

        ret = self.base.resolve()
        to_dnl = []
        if ret:
            for tsi in self.base.transaction:
                print(" "+tsi.active_history_state+" - "+ str(tsi.active))
                if tsi.installed:
                    to_dnl.append(tsi.installed)
            self.base.download_packages(to_dnl)
            self.base.do_transaction()
            print('Language packs installed for: %s' \
                                         % (' '.join(langc.langinstalled)))
            langc.add_langpack_to_installed_list(langc.langinstalled)
        else:
            print('No langpacks to install for: %s' % (' '.join(args)))

        return

class Langpacks(dnf.Plugin):
    """DNF plugin supplying the 'langpacks' commands"""

    name = 'langpacks'
    def __init__(self, base, cli):
        """Initialize the plugin instance."""
        super(Langpacks, self).__init__(base, cli)
        if cli is not None:
            cli.register_command(LangavailableCommand)
            cli.register_command(LanginfoCommand)
            cli.register_command(LanglistCommand)
            cli.register_command(LanginstallCommand)
        logger.debug("initialized Langpacks plugin")

