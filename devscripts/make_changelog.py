import json
import re
import subprocess
from enum import Enum, auto


R'''  # Commit message style
    * Authors are parsed from "Authored by: ..." comments in commit message

* Core
    * No [] prefix
    * "Add options? ..." are moved to top

    Eg: Add option `--alias`
    Eg: Fix `--simulate --max-downloads`

* Core components
    * Prefix path to module (FULL path for extractors)

    Eg: [utils] Improve performance using `functools.cache`
    Eg: [http] Reject broken range before request (#3079)

        ...
        Authored by: Lesmiscore, Jules-A, pukkandan
    Eg: [extractor/generic] Refactor `_extract_rss`

* Extractor
    * Prefix [extractor/<extractor>] or [extractor/<file>]
    * New extractors must have the title "Add( \w+)? extractors?"

    Eg: [extractor/youtube] Add warning for PostLiveDvr
    Eg: [extractor/goodgame] Add extractor (#3686)

        Authored by: nevack
    Eg: [extractor/gronkh] Add playlist extractors (#3337)

        Closes #3300
        Authored by: hatienl0i261299

* "Fix bug in <hash>" / "(Partially )?Revert <hash>"
    * Ignored if the refered commit is in changelog

    Eg: Fix bug in 23326151c45b632c3d5948bd018e80abb370e676
    Eg: Revert acbc64225006964cf52d316e007a77a1b5e2975b

* Cleanup
    * "[cleanup] Misc cleanup( and fixes)?" are merged, others are left as-is

    Eg: [downloader, cleanup] Refactor `report_progress`
'''

R'''  # changelog-override.json can be used to correct the changelog
{
    "correct": {  // Overwrite given commit's information
        "hash": {"prefix": ..., "title": ..., "message": ..., "body": ..., "priority: ...},
        ...
    },
    "remove": [hash, ...],  // Ignore these commits from changelog
    "add": [  // Add these commits to changelog
        {"prefix": ..., "title": ..., "message": ..., "body": ...,  "priority: ...},
        ...
    ],
}
'''

DEFAULT_AUTHOR = 'pukkandan'


class Template:
    def __init__(self, val, formatter='{}', *, delim=', ', for_each='{}'):
        self.formatter = formatter.format if isinstance(formatter, str) else formatter
        self.val = (val if not isinstance(val, (list, tuple, set))
                    else delim.join(map(for_each.format, val)))

    def __str__(self):
        return '' if self.val in (None, '') else self.formatter(self.val)

    @classmethod
    def join(cls, *args):
        return ' '.join(filter(None, (str(cls(x)) if not isinstance(x, cls) else str(x) for x in args)))


class CommitTypes(Enum):
    RELEASE = ('version', )
    PRIORITY = auto()
    UPSTREAM = auto()
    CORE = auto()
    FEATURE = auto()
    COMPONENT = auto()
    UTILS = ('utils', )
    COMPAT = ('compat', )
    DEVSCRIPTS = ('devscripts', )
    BUILD = ('build', 'update')
    TEST = ('test', )
    DOCS = ('docs', )
    CLEANUP = ('cleanup', )
    NEW_EXTRACTOR = auto()
    FIX_EXTRACTOR = auto()
    BUGFIX = auto()
    REVERT = auto()

    def __str__(self):
        return self.name


class Commit:
    HASH_LENGTH = 7
    NO_HASH = '0' * HASH_LENGTH

    def __init__(self, hash, title, message='', *, prefix=None, body=None, priority=False):
        self.hash = hash[:self.HASH_LENGTH]
        if not title:
            raise Exception(f'Commit {hash} has no title')
        self.types = set(self._get_types(title, prefix))  # Also sets title, fix_for
        if priority:
            self.types.add(CommitTypes.PRIORITY)
        self._process_message(message)
        self.body = body

    def _get_types(self, title, prefix):
        if title.startswith('Release'):
            yield CommitTypes.RELEASE

        self.prefix, self.title = re.fullmatch(r'(?s)(?:\[([^\]]+?)\]\s+)?(.+?)(?:\s+\(?#\d+\)?)?', title).groups()
        if prefix is not None:
            self.prefix = prefix
        if self.prefix:
            for typo, correct in {'doc': 'docs', 'extractors': 'extractor'}.items():
                self.prefix = re.sub(rf'\b{re.escape(typo)}\b', correct, self.prefix)
            if ', cleanup' in self.prefix:
                self.prefix = f'cleanup, {self.prefix.replace(", cleanup", "")}'

        for prefix in map(str.strip, (self.prefix or '').split(',')):
            prefix, sub, *_ = prefix.split('/', maxsplit=2) + [None]
            matched = False
            for type_ in CommitTypes:
                if isinstance(type_.value, tuple) and prefix in type_.value:
                    matched = True
                    yield type_
            if not prefix:
                upstream_prefix = 'Update to ytdl-commit-'
                if title.startswith(upstream_prefix):
                    upto = title[len(upstream_prefix):].split(' ')[0]
                    self.title = f'Merge youtube-dl: Upto [commit/{upto[:self.HASH_LENGTH]}](https://github.com/ytdl-org/youtube-dl/commit/{upto})'
                    yield CommitTypes.UPSTREAM
                elif re.match(r'\**Add (option|field)s?\s', self.title):
                    yield CommitTypes.FEATURE
                else:
                    yield CommitTypes.CORE
            elif prefix == 'extractor':
                if sub in ('generic', 'common', None):
                    yield CommitTypes.COMPONENT
                elif re.match(r'(?i)Add\s+(\w+\s+)?extractors?', self.title):
                    yield CommitTypes.NEW_EXTRACTOR
                else:
                    yield CommitTypes.FIX_EXTRACTOR
            elif not matched:
                yield CommitTypes.COMPONENT

        self.fix_for = None
        mobj = re.fullmatch(r'(?i)(?:Bug ?)?Fix(?:es)?(?: bugs?| tests?)? (?:for|in) (?P<commit>[\da-f]{6,})', self.title)
        if mobj:
            self.fix_for = mobj.group('commit')[:self.HASH_LENGTH]
            self.title = f'Fix bug in [{self.fix_for}](https://github.com/yt-dlp/yt-dlp/commit/{mobj.group("commit")})'
            yield CommitTypes.BUGFIX

        mobj = re.fullmatch(r'(?i)(?P<partial>Partially )?Reverts? (?P<commit>[\da-f]{6,})', title)
        if mobj:
            self.fix_for = mobj.group('commit')[:self.HASH_LENGTH]
            self.title = self.title.replace(
                mobj.group('commit'),
                f'[{self.fix_for}](https://github.com/yt-dlp/yt-dlp/commit/{mobj.group("commit")})')
            yield CommitTypes.BUGFIX if mobj.group('partial') else CommitTypes.REVERT

    def _process_message(self, message):
        self.authors = []
        for line in message.splitlines():
            mobj = re.fullmatch(r'(?i)(?:Co-)?Authored[- ]by:? (?P<names>.+)', line)
            if mobj:
                self.authors += map(str.strip, mobj.group('names').split(','))

    def __eq__(self, other):
        if self.hash == self.NO_HASH:
            return self is other
        elif isinstance(other, Commit):
            return self.hash == other.hash
        elif isinstance(other, str):
            return self.hash == other[:self.HASH_LENGTH]
        elif isinstance(other, (int, float)):
            return hash(self) == other
        return False

    def __hash__(self):
        return int(self.hash, 16) + 1

    def __repr__(self):  # For debugging only
        return Template.join(
            self.hash,
            Template(int(''.join('01'[x] for x in self.ordering()[:-1]), 2), '{: 4d}'),
            Template(self.types, '{:>20s}', delim='/'),
            Template(self.fix_for, '({})'),
            Template(self.prefix, '[{}]'),
            self.title,
            Template(sorted(set(self.authors)), 'by {}'),
            '...' if self.body else None
        )

    def __str__(self):
        return Template.join(
            '*', Template(self.prefix, '[{}]'), self.title,
            Template(sorted(set(self.authors)), 'by {}', for_each='[{0}](https://github.com/{0})'),
            Template(self.body, lambda x: f'\n{x}'.replace('\n', '\n    ')),
        )

    def ordering(self):
        cleanup = any(t in self.types for t in (CommitTypes.CLEANUP, CommitTypes.BUGFIX))
        extractor = any(t in self.types for t in (CommitTypes.NEW_EXTRACTOR, CommitTypes.FIX_EXTRACTOR))
        tiers = ((
            CommitTypes.FEATURE in self.types,
        ), (
            CommitTypes.PRIORITY in self.types,
        ), (
            CommitTypes.UPSTREAM in self.types,
        ), (
            CommitTypes.CORE in self.types,
            not cleanup,
        ), (
            not extractor,
            not cleanup,
            CommitTypes.COMPONENT in self.types,
            CommitTypes.UTILS in self.types,
            CommitTypes.BUILD in self.types,
            CommitTypes.COMPAT in self.types,
            CommitTypes.DEVSCRIPTS in self.types,
            CommitTypes.TEST in self.types,
            CommitTypes.DOCS in self.types,
        ), (
            not cleanup,
            CommitTypes.NEW_EXTRACTOR in self.types,
            (self.prefix or '').lower().startswith('extractor/youtube'),
        ))
        rank = (-(x[0] and cndn) for x in tiers for cndn in x)
        return (*rank, ((self.prefix or '').lower(), self.title.lower()))


def git(*args):
    proc = subprocess.run(
        ('git', *args), check=True, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.stdout.strip()


class ReleaseReached(Exception):
    pass


def get_new_commits(override):
    hash_, title, message = None, '', []

    def commit_store():
        nonlocal hash_
        if not hash_:
            return
        commit = Commit(hash_, **{
            'title': title,
            'message': '\n'.join(message),
            **override.get(hash_[:Commit.HASH_LENGTH], {})
        })
        if CommitTypes.RELEASE in commit.types:
            raise ReleaseReached(commit)
        yield commit

    try:
        for line in git('log').splitlines():
            if line.startswith('commit '):
                yield from commit_store()
                hash_, title, message = line.split()[1], '', []
            elif line.startswith('    '):
                if title:
                    message.append(line[4:].rstrip())
                else:
                    title = line.strip()
        yield from commit_store()
    except ReleaseReached:
        return


OVERRIDE_TMPL = '''{
    "correct": {
        "": {}
    },
    "remove": [],
    "add": []
}'''


def load_override(fname):
    with open(fname, encoding='utf-8') as f:
        ret = json.load(f)
    # with open(fname, 'w', encoding='utf-8') as f:
    #     f.write(OVERRIDE_TMPL)
    return ret


def find_commit(hash, commit_list):
    return commit_list[commit_list.index(hash)]


override = load_override('devscripts/changelog-override.json')
commits = list(get_new_commits(override['correct']))
total_commits = len(commits)

has_cleanup, cleanup_authors = True, []
for commit in commits[:]:
    if CommitTypes.REVERT in commit.types and commit.fix_for in commits:
        commits.remove(commit.fix_for)
        commits.remove(commit)
    elif CommitTypes.BUGFIX in commit.types and commit.fix_for in commits:
        base_commit = find_commit(commit.fix_for, commits)
        if not base_commit.authors:
            base_commit.authors = [DEFAULT_AUTHOR]
        base_commit.authors += commit.authors
        commits.remove(commit)
    elif CommitTypes.CLEANUP in commit.types and re.fullmatch(r'(?i)(Misc|Minor)( fixes)?( and)?( cleanup)?( \(see desc\))?', commit.title):
        has_cleanup = True
        cleanup_authors += commit.authors or [DEFAULT_AUTHOR]
        commits.remove(commit)

if set(cleanup_authors) == {DEFAULT_AUTHOR}:
    cleanup_authors = []
if has_cleanup:
    commits.append(Commit(Commit.NO_HASH, '[cleanup] Misc fixes and cleanup'))
    commits[-1].authors = cleanup_authors
for hash_ in override['remove']:
    commits.remove(hash_)
for dct in override['add']:
    commits.append(Commit(Commit.NO_HASH, dct['title'], dct.get('message', ''), body=dct.get('body')))

commits = sorted(commits, key=Commit.ordering)


# ----------------------------------
print(f'Parsed {len(commits)} entries from {total_commits} commits')
print('\n'.join(map(repr, commits)), '\n')
print('\n'.join(map(str, commits)))
