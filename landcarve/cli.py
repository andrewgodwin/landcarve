import click


@click.group()
def main():
    """
    Top-level command entrypoint
    """
    pass


# Import all sub-commands
import landcarve.commands.decifit
import landcarve.commands.fixnodata
import landcarve.commands.pipeline
import landcarve.commands.realise
import landcarve.commands.zfit


if __name__ == "__main__":
    print(id(main))
    main()
