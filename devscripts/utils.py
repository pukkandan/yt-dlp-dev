import functools
import optparse


def read_file(fname):
    with open(fname, encoding='utf-8') as f:
        return f.read()


def write_file(fname, content):
    with open(fname, 'w', encoding='utf-8') as f:
        return f.write(content)


# Get the version without importing the package
def read_version(fname='yt_dlp/version.py'):
    exec(compile(read_file(fname), fname, 'exec'))
    return locals()['__version__']


def get_filename_args(infile=False, default_outfile=None):
    usage = '%prog '
    usage += 'INFILE ' if infile else ''
    usage += '[OUTFILE]' if default_outfile else 'OUTFILE'
    parser = optparse.OptionParser(usage=usage)
    _, args = parser.parse_args()

    num_args = 2 if infile else 1
    if default_outfile and len(args) == num_args - 1:
        args.append(default_outfile)
    elif len(args) != num_args:
        parser.error(parser.get_usage())

    return args if infile else args[0]


def compose_functions(*functions):
    return lambda x: functools.reduce(lambda y, f: f(y), functions, x)
