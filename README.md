# Source Engine Caption Decompiler

Simple Python script to decompile Valve Source Engine caption (.dat) files.

## Info

Compiling captions is a lossy process, so not all information can be retrieved back from the caption file. Namely:
- Comments
- Line order and spacing
- Soundscript names (replaced with their CRC32 hashes)

That last one is the most important, and normally normally that would mean we cannot extract the original names. However since we at least have the hashes it means we can search through existing defined soundscripts and match their hashes with the ones in the compiled file.

You can provide the program the path to these files, either the path to the directory containing `game_sounds_manifest.txt` (which will scan the game directory automatically), or you can manually add soundscape files for it to search. Once provided, any found matches will be replaced in the decompiled output (with any that aren't found staying as the hash). Note that sometimes not all of them will have a match, and this usually means that either the caption is unused or you need to provide more soundscript files.

## Requirements

- [Python](https://www.python.org/downloads/) >= 3.10
- [TeamSpen's srctools module](https://github.com/TeamSpen210/srctools)
    - `pip install srctools`

## Usage

`python CaptionDecompiler.py [PARAMETERS] -i input`

### Parameters

- `--input INPUT, -i INPUT`                       (Required) Path to caption dat file
- `--output OUTPUT, -o OUTPUT`                    Path to output. Defaults to ./samename_d.txt. To disable the '_d' use the '-ns' switch

- `--sound-dir [SOUND_DIR], -sd [SOUND_DIR]`      Directory containing soundscripts and game_sounds_manifest.txt. These will be searched to match soundscript name hashes. By default this automatically attempts to be found. To disable this behavior, use the '-nas' switch
- `--sound-script SOUND_SCRIPT, -ss SOUND_SCRIPT` Direct path to a soundscript file. Can add as many as you want
- `--sound-name SOUND_NAME, -sn SOUND_NAME`       A direct soundscript name to match against. Can add as many as you want
- `--sound-list SOUND_LIST, -sl SOUND_LIST`       A file containing a newline-separated list of soundscript names. Makes no attempt to validate this format, so be careful
- `--no-auto-sounds, -nas`                        Disables automatically attempting to find soundscript files

- `--language LANGUAGE, -l LANGUAGE`              Manually set the output language. Default is automatically guessed based on the filename. If your filename has a non-standard format you should probably set this, otherwise it will either be incorrect or blank
- `--same-hashes, -sh`                            Ensures all unfound soundscript names compile to the same hash. May increase computation time dramatically if there are a lot of missing names

- `--no-suffix, -ns`                              Disables adding the '_d' suffix to the end of the automatic file name
- `--padding PADDING, -p PADDING`                 (AKA tab-size) Padding size for the output. Defaults to 4. Note that your editor must match this size to display alignment correctly (if using tabs)
- `--no-align, -na`                               Disables output caption alignment
- `--tabs, -t`                                    DISABLES tabs for padding, and instead uses spaces

- `--accept, -a`                                  Automatically accepts all dialogs. Right now there is only an output file overwrite confirmation
- `--verbose VERBOSE, -v VERBOSE`                 Increase output verbosity (0 - 2). Defaults to 0

- `-h, --help`                                    Shows the help message and exits