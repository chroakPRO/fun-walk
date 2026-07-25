#!/usr/bin/env python3
"""Extract only the two NMD object-coverage rasters used by the spot scorer."""

from argparse import ArgumentParser
from pathlib import Path
from zipfile import ZipFile, BadZipFile
import os
import shutil


LAYERS = {
    'low_vegetation_coverage.tif': 'Objekt_tackning_hojdintervall_0_5_till_5',
    'tall_vegetation_coverage.tif': 'Objekt_tackning_hojdintervall_5_till_45',
}


def find_member(archive: ZipFile, fragment: str) -> str:
    candidates = [
        name for name in archive.namelist()
        if fragment.lower() in Path(name).name.lower() and name.lower().endswith(('.tif', '.tiff'))
    ]
    if not candidates:
        raise ValueError(f'Could not find a GeoTIFF containing “{fragment}” in the archive.')
    return max(candidates, key=lambda name: archive.getinfo(name).file_size)


def extract_layer(archive: ZipFile, member: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + '.part')
    with archive.open(member) as source, temporary.open('wb') as output:
        shutil.copyfileobj(source, output, length=1024 * 1024)
    os.replace(temporary, destination)


def main() -> None:
    parser = ArgumentParser(
        description='Import the two NMD 2023 coverage layers without retaining the other archive contents.',
    )
    parser.add_argument('archive', type=Path, help='Downloaded NMD object-height/object-coverage ZIP archive')
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path(__file__).resolve().parents[1] / 'data' / 'nmd',
        help='Destination directory (default: data/nmd)',
    )
    parser.add_argument(
        '--low-only',
        action='store_true',
        help='Extract only the 0.5–5 m eye-level coverage layer to save disk space',
    )
    args = parser.parse_args()
    if not args.archive.is_file():
        parser.error(f'Archive does not exist: {args.archive}')

    try:
        with ZipFile(args.archive) as archive:
            layers = list(LAYERS.items())[:1] if args.low_only else LAYERS.items()
            for output_name, fragment in layers:
                member = find_member(archive, fragment)
                destination = args.output_dir / output_name
                print(f'Extracting {Path(member).name} -> {destination}')
                extract_layer(archive, member, destination)
                print(f'  {destination.stat().st_size / (1024 ** 3):.2f} GiB')
    except (BadZipFile, ValueError) as error:
        parser.error(str(error))

    print('NMD vegetation coverage is ready; the backend will detect it on the next search.')


if __name__ == '__main__':
    main()
