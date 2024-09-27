import argparse
from io import TextIOWrapper
from math import ceil, floor
import os
import re
import sys
from typing import Tuple
import zlib

from srctools.keyvalues import Keyvalues

# From https://stackoverflow.com/a/71112312
def ranged_type(value_type, min_value, max_value):
    """
    Return function handle of an argument type function for ArgumentParser checking a range:
        min_value <= arg <= max_value

    Parameters
    ----------
    value_type  - value-type to convert arg to
    min_value   - minimum acceptable argument
    max_value   - maximum acceptable argument

    Returns
    -------
    function handle of an argument type function for ArgumentParser


    Usage
    -----
        ranged_type(float, 0.0, 1.0)

    """
    
    def range_checker(arg: str):
        try:
            f = value_type(arg)
        except ValueError:
            raise argparse.ArgumentTypeError(f'must be a valid {value_type}')
        if f < min_value or f > max_value:
            raise argparse.ArgumentTypeError(f'must be within [{min_value}, {max_value}]')
        return f
    
    # Return function handle to checking function
    return range_checker

# Create arguments globally

parser = argparse.ArgumentParser(description="Decompiles Source Engine caption .dat files back into text")

# IO
parser.add_argument("--input", "-i", required=True, type=argparse.FileType("r"), help="Path to caption dat file")
parser.add_argument("--output", "-o", type=str, help="Path to output. Defaults to samedir/samename_d.txt. To disable the '_d' use the '-ns' switch")

# Soundscript matching inputs
gsArg = parser.add_argument("--sound-dir", "-sd", nargs="?", const="Auto", help="Directory containing soundscripts and game_sounds_manifest.txt. These will be searched to match soundscript name hashes. If SOUND_DIR is not provided, attempts to automatically find game_sounds_manifest.txt based on the location of the input")
parser.add_argument("--sound-script", "-ss", action="append", type=str, help="Direct path to a soundscript file. Can add as many as you want")
parser.add_argument("--sound-name", "-sn", action="append", type=str, help="A direct soundscript name to match against. Can add as many as you want")
parser.add_argument("--sound-list", "-sl", action="append", type=argparse.FileType("r"), help="A file containing a newline-separated list of soundscript names. Makes no attempt to validate this format, so be careful")

# Misc
parser.add_argument("--language", "-l", action="store", type=str, help="Manually set the output language. Default is automatically guessed based on the filename. If your filename has a non-standard format you should probably set this, otherwise it will either be incorrect or blank")
parser.add_argument("--same-hashes", "-sh", action="store_true", help="Ensures all unfound soundscript names compile to the same hash. May increase computation time dramatically if there are a lot of missing names")

# Output formatting
parser.add_argument("--no-suffix", "-ns", action="store_true", help="Disables adding the '_d' suffix to the end of the automatic file name")
parser.add_argument("--padding", "-p", action="store", type=int, default=4, help="(AKA tab-size) Padding size for the output. Defaults to 4. Note that your editor must match this size to display alignment correctly (if using tabs)")
parser.add_argument("--no-align", "-na", action="store_true", help="Disables output caption alignment")
parser.add_argument("--tabs", "-t", action="store_true", help="DISABLES tabs for padding, and instead uses spaces")

# Meta
parser.add_argument("--accept", "-a", action="store_true", help="Automatically accepts all dialogs. Right now there is only an output file overwrite confirmation")
parser.add_argument("--verbose", "-v", action="store", type=ranged_type(int, 0, 2), default=0, help="Increase output verbosity (0 - 2). Defaults to 0")

args = parser.parse_args()

def main():
    filepath = os.path.dirname(args.input.name)
    
    if (args.sound_dir != "Auto"):
        if (args.sound_dir and not os.path.exists(args.sound_dir)): raise argparse.ArgumentError(gsArg, "Path does not exist: " + args.sound_dir)
        if (args.sound_dir and     os.path.isfile(args.sound_dir)): raise argparse.ArgumentError(gsArg, "Must be a directory")
    else:
        # Automatically check for path and warn if it is not found
        args.sound_dir = os.path.join(filepath, os.path.pardir, "scripts")
    if (not os.path.exists(args.sound_dir)):
        args.sound_dir = None
        print("Warning: Could not find game_sounds_manifest.txt")
    
    if (filepath == "."): filepath = ""
    filenameNoExt = os.path.splitext(os.path.basename(args.input.name))[0]
    
    language = ""
    if (args.language): language = args.language
    else:
        # Get language based on caption file name
        # The format shouldn't be a problem under most circumstances but it's better to check anyway in case the file name doesn't follow the standard one for whatever reason
        # NOTE: Technically this is a bit lenient on the format so the auto detected language might be bad for nonstandard formats.
        #   I don't know how I would fix this other than at least detecting the beginning of the name, since there is only a limited set of those that are usually used
        #   I guess there is also a limited number of languages too but that's a bit much to check for something so frivolous that will likely never be a problem anyway
        if (re.match(r"[a-zA-Z0-9]+_[a-zA-Z0-9]+", filenameNoExt)): language = filenameNoExt.split("_")[1]
        else: print("WARNING: Input filename does not match regular format, and no language specified. Language will not be set!")
    
    # Check output file
    outputFile = ""
    if (args.output): outputFile = args.output
    else:
        if (filepath == "."): outputFile = filepath
        outputFile += filenameNoExt
        if (not args.no_suffix): outputFile += "_d.txt"
    if (os.path.exists(outputFile)):
        print("WARNING: Output will overwrite " + outputFile)
        if (not args.accept):
            shouldOverwrite = input("Do you want to overwrite the file? [Y/n]: ")
            if (shouldOverwrite.lower() == "n"):
                print("Process canceled")
                sys.exit()
    
    with open(args.input.name, mode="rb") as file:
        # Get header data
        MAGIC = file.read(4).decode("ascii")
        if (MAGIC != "VCCD"):
            print("ERROR: Invalid caption file (MAGIC != \"VCCD\")")
            sys.exit()
        
        # Get header data. We don't need all of this but we get it just in case
        VERSION = int.from_bytes(file.read(4), "little") # Caption file version. This is always 1 from what I know
        if (VERSION != 1):
            print(f"ERROR: Invalid file version {VERSION}. Version must be 1!")
            sys.exit()
        
        NUM_BLOCKS     = int.from_bytes(file.read(4), "little") # Number of blocks
        BLOCK_SIZE     = int.from_bytes(file.read(4), "little") # Size of each caption block. Usually 8192
        DIRECTORY_SIZE = int.from_bytes(file.read(4), "little") # Number of entries in the directory
        DATA_OFFSET    = int.from_bytes(file.read(4), "little") # Offset where raw data starts
        
        HEADER_SIZE = 24
        DIRECTORY_ENTRY_SIZE = 4 + 4 + 2 + 2 # crc hash + block index + offset + length
        DICT_PADDING = 512 - (HEADER_SIZE + DIRECTORY_SIZE * DIRECTORY_ENTRY_SIZE) % 512
        
        if (args.verbose >= 2):
            print(f"MAGIC: {MAGIC}")
            print(f"VERSION: {hex(VERSION)}") 
            print(f"BLOCKS: {hex(NUM_BLOCKS)}")
            print(f"BLOCK_SIZE: {hex(BLOCK_SIZE)}")
            print(f"DIRECTORY_SIZE: {hex(DIRECTORY_SIZE)}")
            print(f"DATA_OFFSET: {hex(DATA_OFFSET)}")
            print(f"DIRECTORY_OFFSET: {hex(file.tell())}")
            print(f"HEADER_SIZE: {HEADER_SIZE}")
            print(f"DIRECTORY_ENTRY_SIZE: {hex(DIRECTORY_ENTRY_SIZE)}")
            print(f"DICT_PADDING: {hex(DICT_PADDING)}")
            print("------------------------------------------------")
        
        # Get all directory entries
        captionDirEntries = getDirEntries(file, HEADER_SIZE, DIRECTORY_SIZE)
        
        # Read all sound files and extract their soundscapes names
        soundscriptCandidates = getSoundscriptsFromFiles()
        
        # Read all caption blocks
        finalCaptions = readCaptionBlocks(file, captionDirEntries, soundscriptCandidates, DATA_OFFSET, BLOCK_SIZE)
        
        # Compute maximum caption length, for padding purposes
        maxCaptionLength = 0
        largestCaption = ""
        for name in finalCaptions:
            if (len(name) > maxCaptionLength):
                maxCaptionLength = len(name)
                largestCaption = name
        
        if (args.verbose >= 2): print(f"MAX CAPTION LENGTH: {maxCaptionLength}, PROVIDED BY: \"{largestCaption}\"")
        
        maxCaptionLength += 2 # Account for quotes
        if (not args.no_align and args.padding > 0 and (maxCaptionLength % args.padding) == 0): maxCaptionLength += 1 # Make sure that the padding never ends up being 0 (meaning the key+values are touching each other)
        
        if (args.verbose >= 2): print(f"MAX CAPTION LENGTH WITH ALIGNMENT: {maxCaptionLength}")
        
        # Write captions
        writeCaptions(outputFile, finalCaptions, maxCaptionLength, language)
    
    print(f"Finished. Wrote file at {outputFile}")

# Reads all captions from the file and returns a dict containing the name (or hash) and caption
def readCaptionBlocks(file:TextIOWrapper, captionDirEntries:dict, soundscriptCandidates:dict, DATA_OFFSET:int, BLOCK_SIZE:int) -> dict:
    attemptingHashMatching = len(soundscriptCandidates) > 0
    
    print("Reading caption blocks", end="")
    if (attemptingHashMatching): print(" and attempting to match hashes and names", end="")
    print("...")
    
    verbosePrintPadding = ""
    maxCapLen = 10
    if (args.verbose >= 2):
        # HACK: We don't have access to the actual maxCaptionLength yet, so we fake it by getting the max length from all candidates
        #   We could preemptively calculate the actual length, but then we would have to do 2 loops through all captions, which is inefficient.
        #   This works good enough, worst case scenario the padding is a bit too large. Otherwise we can just set a static max padding, but I feel like that sucks more
        if (attemptingHashMatching):
            for entry in soundscriptCandidates.values():
                if (len(entry) > maxCapLen):
                    maxCapLen = len(entry)
        
        for _ in range(maxCapLen - 4): verbosePrintPadding += " "
        
        # NOTE: I don't actually know the full specifications of caption files, but assuming the block count can exceed 100,000 the padding here may not always be enough
        #   That would be exceedingly rare if even possible, and likely no caption files even exist with that size, so this is fine
        print("------------------------------------------------")
        print("| BLOCK".ljust(8, " ") + f"| NAME{verbosePrintPadding} | CAPTION")
    
    # Read each segment and add to output
    # Also attempts to match hashes if the user provided the files
    blockIndex = 0
    ssHashMatches = 0
    captionLineIndex = 6 # Simulates line count in output file. 6 is the line where the captions start
    finalCaptions = {}
    file.seek(DATA_OFFSET)
    for entry in captionDirEntries:
        # Go to correct block
        if (entry["index"] > blockIndex): file.seek(DATA_OFFSET + (BLOCK_SIZE * entry["index"]))
        blockIndex = entry["index"]
        
        # Get current caption
        caption = ""
        for _ in range(int(entry["length"]/2)-1):
            caption += file.read(2).decode("utf_16_le")
        file.read(2) # Null terminator
        
        captionName = str(entry["hash"]).rjust(10, "0")
        if (attemptingHashMatching):
            if (entry["hash"] in soundscriptCandidates):
                captionName = str(soundscriptCandidates[entry["hash"]])
                ssHashMatches+=1
            else:
                if (args.verbose >= 2): print("|>", end="")
                if (args.verbose >= 1): print(f"\tCould not find match for hash {captionName} (line {captionLineIndex})", end="")
                # Append new string to the end of the caption name (which is just the original hash since we didn't find the real name)
                #   This new appended bit ensures that the hash of this new name matches the original, which allows us to recompile the output exactly the same as the original
                #   For most cases this is probably unnecessary, since in order for it to matter it would need to exist as a soundscape somewhere (which we should have already found by now)
                # NOTE: This still doesn't technically produce an "identical" compiled output since the new caption names will be sorted differently by the compiler, but that shouldn't matter for 99.99% of cases
                #   We could theoretically fix this by prepending some starting characters to match the order of the surrounding caption names alphabetically, but that's pretty much useless like I said
                if (args.same_hashes == True):
                    if (args.verbose >= 1): print(". Generating new name... ")
                    captionName = generateStrWithNewCRC(str(entry["hash"]).rjust(10, "0")+".", entry["hash"])
                    if (args.verbose >= 2): print(f"|>>\t\tNEW NAME GENERATED: {captionName}")
                elif (args.verbose >= 1): print() # Newline
        
        captionLineIndex+=1
        
        finalCaptions[captionName] = caption
        
        if (args.verbose >= 2):
            verbosePrintPadding = ""
            for _ in range(maxCapLen - len(captionName)): verbosePrintPadding += " "
            print("| " + str(entry["index"]).rjust(5, " ") + f" | {captionName}{verbosePrintPadding} | {caption}")
    
    if (args.verbose >= 2):
        verbosePrintPadding = ""
        for _ in range(maxCapLen - 4): verbosePrintPadding += " "
        print("| BLOCK".ljust(8, " ") + f"| NAME{verbosePrintPadding} | CAPTION")
        print("------------------------------------------------")
    
    # Theoretically all relevant subtitles should be found (if the user provided the proper paths/files to check), however there might be unused ones left over that no longer exist as soundscripts.
    #   In any case, this means that the relevant game never uses this caption anyway and it is up to the user to remake it if they want to use it.
    #   If there is an existing subtitle .txt file, (then you shouldn't even be using this decompiler anyway, but) it probably has the actual unused soundscript names in it
    print(f"Hashes found: {ssHashMatches}, Expected: {len(captionDirEntries)}")
    if (ssHashMatches != len(captionDirEntries)):
        print(f"WARNING: Did not find names for {len(captionDirEntries) - ssHashMatches} captions! (Either we couldn't find them or they are unused)")
    else:
        print("All caption names found")
    
    return finalCaptions

# Gets all caption directory entries
def getDirEntries(file:TextIOWrapper, HEADER_SIZE:int, DIRECTORY_SIZE:int) -> list:
    print("Retrieving captions...")
    
    # Make sure file is at the correct location
    file.seek(HEADER_SIZE)
    
    if (args.verbose >= 2):
        print("------------------------------------------------")
        print("| CRC HASH".ljust(13, " ") + "| BLOCK".ljust(8, " ") + "| OFFSET".ljust(9, " ") + "| LENGTH")
    
    entries = []
    for _ in range(DIRECTORY_SIZE):
        HASH        = int.from_bytes(file.read(4), "little")
        BLOCK_INDEX = int.from_bytes(file.read(4), "little")
        OFFSET      = int.from_bytes(file.read(2), "little")
        LENGTH      = int.from_bytes(file.read(2), "little")
        
        entries.append({
            "hash"  : HASH,
            "index" : BLOCK_INDEX,
            "offset": OFFSET,
            "length": LENGTH
        })
        
        if (args.verbose >= 2):
            print("| " + str(hex(HASH)).ljust(10, " ") + " | " + str(BLOCK_INDEX).rjust(5, " ") + " | " + str(hex(OFFSET)).ljust(6, " ") + " | " + str(LENGTH).ljust(3, " "))
    
    if (args.verbose >= 2):
        print("| CRC HASH".ljust(13, " ") + "| BLOCK".ljust(8, " ") + "| OFFSET".ljust(9, " ") + "| LENGTH")
        print("------------------------------------------------")
    
    return entries

def getSoundscriptsFromFiles() -> dict:
    soundscriptCandidates = {}
    
    # Only perform matching if anything was provided by the user
    if (args.sound_dir or args.sound_script or args.sound_name or args.sound_list):
        foundSoundscripts = []
        gameSoundsFiles = []
        
        # Read game_sounds_manifest and extract all referenced files
        if (args.sound_dir):
            path = os.path.join(args.sound_dir, "game_sounds_manifest.txt")
            with open(path, mode="r") as manifest:
                for fileEntry in Keyvalues.parse(manifest.read())[0]:
                    entry = fileEntry.serialise().replace("\"", "").split()
                    if (entry[0] == "precache_file"): gameSoundsFiles.append(os.path.abspath(os.path.join(args.sound_dir, os.pardir, entry[1])))
        
        # Add manual soundscript file entries
        if (args.sound_script):
            for fileEntry in args.sound_script:
                gameSoundsFiles.append(fileEntry)
        
        # Generic list of soundscript names
        if (args.sound_list):
            for fileEntry in args.sound_list:
                for entry in fileEntry.read().splitlines():
                    foundSoundscripts.append(entry)
        
        if (args.sound_name):
            for entry in args.sound_name:
                foundSoundscripts.append(entry)
        
        # Read every file and extract all soundscript names
        if (len(gameSoundsFiles) > 0):
            print("Extracting soundscript names...")
            for fileEntry in gameSoundsFiles:
                if (args.verbose >= 1): print(f"\tReading {fileEntry}")
                
                ssCount = 0
                with open(fileEntry, mode="r") as file:
                    for soundScriptName in Keyvalues.parse(file.read()).as_dict():
                        foundSoundscripts.append(soundScriptName)
                        ssCount+=1
                
                if (args.verbose >= 1): print(f"\t\tFound {ssCount} soundscapes in file")
            
            print(f"Found a total of {len(foundSoundscripts)} soundscripts, {len(set(foundSoundscripts))} unique")
            foundSoundscripts = list(set(foundSoundscripts)) # Remove duplicates
        else:
            print(f"Checking {len(foundSoundscripts)} soundscript names")
        
        # Get soundscript hashes
        print("Hashing soundscript names...")
        for souncscript in foundSoundscripts:
            soundscriptCandidates[zlib.crc32(bytes(souncscript, "utf-8"))] = souncscript
    else:
        print("No soundscript files provided. Skipping name hash matching")
    
    return soundscriptCandidates

# Writes final caption string and outputs to file
def writeCaptions(outputFile:TextIOWrapper, finalCaptions:dict, maxCaptionLength:int, language:str):
    print("Writing captions...")
    
    padChar = "\t"
    if (args.tabs): padChar = ""
    if (args.padding > 0):
        if (args.tabs):
            padChar = ""
            for _ in range(args.padding):
                padChar += " "
        
        if (args.verbose >= 2 and not args.no_align):
                verbosePrintPadding = ""
                for _ in range(maxCaptionLength-2 - 7): verbosePrintPadding += " "
                print(f"| STRING {verbosePrintPadding}| PADDING")
    
    output = "\"lang\"\n{\n" + padChar + "\"Language\" \"" + language + "\"\n" + padChar + "\"Tokens\"\n" + padChar + "{\n"
    for name in finalCaptions:
        paddingAlignment = padChar
        if (not args.no_align and args.padding > 0):
            paddingAlignment = ""
            innerPadChar = padChar # (Only if using spaces) We don't always use the same number of spaces to align in here
            
            # Calculate actual padding alignment
            padAmount = ceil(maxCaptionLength / args.padding) - floor((len(name)+2) / args.padding)
            if (args.tabs):
                innerPadChar = " "
                padAmount = (maxCaptionLength + (args.padding - (maxCaptionLength % args.padding))) - (len(name)+2)
            
            if (args.verbose >= 2):
                verbosePrintPadding = ""
                for _ in range(maxCaptionLength-2 - len(name)): verbosePrintPadding += " "
                print(f"| {name}{verbosePrintPadding}| {padAmount}")
            
            for _ in range(padAmount):
                paddingAlignment += innerPadChar
        else:
            print(f"WRITING {name}")
        
        output += f"{padChar}{padChar}\"{name}\"{paddingAlignment}\"{finalCaptions[name]}\"\n"
    
    if (args.verbose >= 2 and not args.no_align and args.padding > 0):
        verbosePrintPadding = ""
        for _ in range(maxCaptionLength-2 - 7): verbosePrintPadding += " "
        print(f"| STRING {verbosePrintPadding}| PADDING")
    
    # Final output
    with open(outputFile, mode="w", encoding="utf16") as file:
        file.write(output + padChar + "}\n}")

# Takes a string and appends ascii characters to the end of it, such that it's crc matches the requested crc
def generateStrWithNewCRC(string: str, newcrc: int, printstatus: bool = False):
    # 
    # CRC-32 forcer (Python)
    # 
    # Copyright (c) 2020 Project Nayuki
    # https://www.nayuki.io/page/forcing-a-files-crc-to-any-value
    # 
    # This program is free software: you can redistribute it and/or modify
    # it under the terms of the GNU General Public License as published by
    # the Free Software Foundation, either version 3 of the License, or
    # (at your option) any later version.
    # 
    # This program is distributed in the hope that it will be useful,
    # but WITHOUT ANY WARRANTY; without even the implied warranty of
    # MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    # GNU General Public License for more details.
    # 
    # You should have received a copy of the GNU General Public License
    # along with this program (see COPYING.txt).
    # If not, see <http://www.gnu.org/licenses/>.
    # 
    # 
    # Modified to work with our decompiler
    # Modified to accept a string instead of a path, and also made it work with the above function
    # Also all required functions were expanded / merged with this scope
    def modify_string_crc32(string: str, newcrc: int, printstatus: bool = False) -> str:
        POLYNOMIAL: int = 0x104C11DB7  # Generator polynomial. Do not modify, because there are many dependencies
        
        def reverse32(x: int) -> int:
            y: int = 0
            for _ in range(32):
                y = (y << 1) | (x & 1)
                x >>= 1
            return y
        
        # Returns polynomial x multiplied by polynomial y modulo the generator polynomial.
        def multiply_mod(x: int, y: int) -> int:
            # Russian peasant multiplication algorithm
            z: int = 0
            while y != 0:
                z ^= x * (y & 1)
                y >>= 1
                x <<= 1
                if (x >> 32) & 1 != 0:
                    x ^= POLYNOMIAL
            return z
        
        # Returns the reciprocal of polynomial x with respect to the modulus polynomial m.
        def reciprocal_mod() -> int:
            # Computes polynomial x divided by polynomial y, returning the quotient and remainder.
            def divide_and_remainder(x: int, y: int) -> Tuple[int,int]:
                if y == 0:
                    raise ValueError("Division by zero")
                if x == 0:
                    return (0, 0)
                ydeg: int = y.bit_length() - 1
                z: int = 0
                for i in range((x.bit_length() - 1) - ydeg, -1, -1):
                    if (x >> (i + ydeg)) & 1 != 0:
                        x ^= y << i
                        z |= 1 << i
                return (z, x)
            
            # pow_mod: Returns polynomial x to the power of natural number y modulo the generator polynomial.
            x: int = 1
            a = 2
            b = (length - offset) * 8
            while b != 0:
                if b & 1 != 0:
                    x = multiply_mod(x, a)
                a = multiply_mod(a, a)
                b >>= 1
            
            # Based on a simplification of the extended Euclidean algorithm
            y: int = x
            x = POLYNOMIAL
            a: int = 0
            b: int = 1
            while y != 0:
                q, r = divide_and_remainder(x, y)
                c = a ^ multiply_mod(q, b)
                x = y
                y = r
                a = b
                b = c
            if x == 1:
                return a
            else:
                raise ValueError("Reciprocal does not exist")
        
        # Convert string to bytes
        string = bytearray(string, "ascii")
        
        length: int = len(string)
        offset = length - 4
        if offset + 4 > length:
            raise ValueError("Byte offset plus 4 exceeds file length")
        
        # Read entire string and calculate original CRC-32 value
        crc = zlib.crc32(string)
        if printstatus:
            print(f"Original CRC-32: {reverse32(crc):08X}")
        
        # Compute the change to make
        delta: int = crc ^ newcrc
        
        # delta = multiply_mod(reciprocal_mod(pow_mod(2, (length - offset) * 8)), reverse32(delta))
        delta = multiply_mod(reciprocal_mod(), reverse32(delta))
        
        # Patch 4 bytes in string
        for i in range(4):
            string[offset+i] ^= (reverse32(delta) >> (i * 8)) & 0xFF
        if printstatus:
            print("Computed and wrote patch")
        
        # Recheck entire string
        if zlib.crc32(string) != newcrc:
            raise AssertionError("Failed to update CRC-32 to desired value")
        elif printstatus:
            print("New CRC-32 successfully verified")
        
        return string
    
    # Custom code to generate the new chars
    USABLE_CHARS = "0123456789abcdefghijklmnopqrstuvwxyz" # Must all be lowercase
    for c1 in USABLE_CHARS:
        for c2 in USABLE_CHARS:
            for c3 in USABLE_CHARS:
                for c4 in USABLE_CHARS:
                    # Add new values to string and pass to the function for modification
                    newString = modify_string_crc32(string + c1 + c2 + c3 + c4 + "0000", newcrc, printstatus)
                    end = "-" # Purposefully bad char by default
                    # Check for invalid characters by detecting when decode fails
                    try: end = newString.decode()[-4:]
                    except: pass
                    # Check for characters outside the set. If they are all within, that means we have a good match
                    if (not (len([c for c in end if not c in USABLE_CHARS]) > 0)):
                        return newString.decode()
    return -1

if (__name__ == "__main__"): main()
