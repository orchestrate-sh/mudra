import click
import os


class Click_Formatter(click.Option):
    def __init__(self, *args, **kwargs):
        super(Click_Formatter, self).__init__(*args, **kwargs)

    def handle_parse_result(self, ctx, opts, args):
        if 'extravars' in opts:
            if "=" not in opts['extravars']:
                if not os.path.exists(opts['extravars']):
                    raise click.BadParameter(
                        "The file {} does not exist".format(opts['extravars']))
        input_args = []
        if 'args' not in opts:
            raise click.BadParameter("No arguments provided")
        for val in opts['args']:
            if '=' not in val:
                raise click.BadParameter(
                    'Please use format key="value-1,value-2,..,value-n"')
            input_args.append(val.split('='))
        input_args = dict(input_args)
        return super(Click_Formatter, self).handle_parse_result(ctx, opts, args)
