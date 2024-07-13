import click


@click.group()
def main():
    """
    Top-level command entrypoint
    """
    pass


# Import all sub-commands
import landcarve.commands.bulkget
import landcarve.commands.contour_image
import landcarve.commands.decifit
import landcarve.commands.decimate
import landcarve.commands.elevalue
import landcarve.commands.exactfit
import landcarve.commands.fixnodata
import landcarve.commands.flipy
import landcarve.commands.lasdem
import landcarve.commands.pipeline
import landcarve.commands.merge
import landcarve.commands.realise
import landcarve.commands.smooth
import landcarve.commands.stats
import landcarve.commands.step
import landcarve.commands.tileimage
import landcarve.commands.tilesplit
import landcarve.commands.zfit


if __name__ == "__main__":
    print(id(main))
    main()
