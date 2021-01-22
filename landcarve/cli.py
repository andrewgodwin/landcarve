import click


@click.group()
def main():
    """
    Top-level command entrypoint
    """
    pass


# Import all sub-commands
import landcarve.commands.contour_image
import landcarve.commands.decifit
import landcarve.commands.fixnodata
import landcarve.commands.lasdem
import landcarve.commands.pipeline
import landcarve.commands.realise
import landcarve.commands.smooth
import landcarve.commands.step
import landcarve.commands.tileimage
import landcarve.commands.zfit


if __name__ == "__main__":
    print(id(main))
    main()
