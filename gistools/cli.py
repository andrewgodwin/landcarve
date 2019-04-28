import click


@click.group()
@click.option("--nodata", default=-1000.0, help="NODATA value.")
@click.pass_context
def main(ctx, nodata):
    """
    Top-level command entrypoint
    """
    # Set NODATA values
    ctx.obj["nodata"] = nodata


# Import all sub-commands
import gistools.commands.decifit


if __name__ == "__main__":
    print(id(main))
    main()
