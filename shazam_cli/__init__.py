import asyncio
import base64
import json
import re
from pathlib import Path

import aiohttp
import click
import mutagen
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from shazamio import Shazam, Serialize


@click.group()
def cli():
    """Simple Shazam CLI using ShazamIO."""


@cli.command()
@click.argument("file", type=click.Path(exists=True))
def recognize(file):
    """Recognize a track from an audio file."""

    async def _run():
        shazam = Shazam()
        result = await shazam.recognize(file)
        click.echo(json.dumps(result, indent=2, ensure_ascii=False))

    asyncio.run(_run())


@cli.command()
@click.argument("artist_id", type=int)
def artist(artist_id):
    """Get information about an artist by their Shazam ID."""

    async def _run():
        shazam = Shazam()
        data = await shazam.artist_about(artist_id)
        serialized = Serialize.artist(data)
        click.echo(f"Name: {serialized.name}")
        click.echo(f"Verified: {serialized.verified}")
        click.echo(f"Avatar: {serialized.avatar}")
        click.echo(f"\nRaw data:")
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))

    asyncio.run(_run())


@cli.command()
@click.argument("track_id", type=int)
def track(track_id):
    """Get information about a track by its Shazam ID."""

    async def _run():
        shazam = Shazam()
        data = await shazam.track_about(track_id=track_id)
        serialized = Serialize.track(data=data)
        click.echo(f"Title: {serialized.title}")
        click.echo(f"Subtitle: {serialized.subtitle}")
        click.echo(f"\nRaw data:")
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))

    asyncio.run(_run())


def _extract_section_metadata(raw_track: dict) -> dict[str, str]:
    """Extract metadata (Album, Label, Released) from the SONG section."""
    result = {}
    for section in raw_track.get("sections", []):
        if section.get("type") != "SONG":
            continue
        for item in section.get("metadata", []):
            result[item["title"]] = item["text"]
    return result


async def _download_image(url: str) -> bytes | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception:
        return None


def _embed_cover_art(file_path: str, cover_data: bytes) -> None:
    audio = mutagen.File(file_path)
    if audio is None:
        return

    if isinstance(audio, FLAC):
        pic = Picture()
        pic.type = 3
        pic.mime = "image/jpeg"
        pic.desc = "front cover"
        pic.data = cover_data
        audio.clear_pictures()
        audio.add_picture(pic)
    elif isinstance(audio, MP3):
        if audio.tags is None:
            audio.add_tags()
        audio.tags.delall("APIC")
        audio.tags.add(APIC(
            encoding=3,
            mime="image/jpeg",
            type=3,
            desc="front cover",
            data=cover_data,
        ))
    elif isinstance(audio, MP4):
        if audio.tags is None:
            audio.add_tags()
        audio.tags["covr"] = [
            MP4Cover(cover_data, imageformat=MP4Cover.FORMAT_JPEG)
        ]
    elif hasattr(audio, "tags") and hasattr(audio.tags, "get"):
        # OGG Vorbis / Opus — base64-encoded FLAC Picture block
        pic = Picture()
        pic.type = 3
        pic.mime = "image/jpeg"
        pic.desc = "front cover"
        pic.data = cover_data
        audio["metadata_block_picture"] = [
            base64.b64encode(pic.write()).decode("ascii")
        ]
    else:
        return

    audio.save()


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--move", is_flag=True, help="Delete the original file after renaming.")
def tag(file, move):
    """Recognize an audio file and write Shazam metadata as tags."""

    async def _run():
        shazam = Shazam()

        click.echo(f"Recognizing {file}...")
        result = await shazam.recognize(file)

        raw_track = result.get("track")
        if not raw_track:
            click.echo("No match found.", err=True)
            raise SystemExit(1)

        track_id = int(raw_track["key"])
        click.echo(f"Match: {raw_track.get('title')} - {raw_track.get('subtitle')}")

        artist_id = None
        for artist_entry in raw_track.get("artists", []):
            artist_id = artist_entry.get("adamid") or artist_entry.get("id")
            if artist_id:
                artist_id = int(artist_id)
                break

        click.echo("Fetching track details...")
        track_data = await shazam.track_about(track_id=track_id)
        track_info = Serialize.track(data=track_data)

        genres = []
        if artist_id:
            click.echo(f"Fetching artist details (ID: {artist_id})...")
            try:
                artist_data = await shazam.artist_about(artist_id)
                artist_info = Serialize.artist(artist_data)
                genres = artist_info.genres or []
            except Exception:
                click.echo("  Could not fetch artist info, skipping genres.")

        section_meta = _extract_section_metadata(track_data)

        tags = {}
        tags["title"] = track_info.title
        tags["artist"] = track_info.subtitle
        if genres:
            tags["genre"] = genres[0]
        if "Album" in section_meta:
            tags["album"] = section_meta["Album"]
        if "Released" in section_meta:
            tags["date"] = section_meta["Released"]
        if "Label" in section_meta:
            tags["organization"] = section_meta["Label"]

        cover_url = track_info.photo_url or raw_track.get("images", {}).get("coverarthq")
        cover_data = None
        if cover_url:
            click.echo("Downloading cover art...")
            cover_data = await _download_image(cover_url)

        click.echo(f"Writing tags to {file}...")
        audio = mutagen.File(file, easy=True)
        if audio is None:
            click.echo("Unsupported audio format.", err=True)
            raise SystemExit(1)
        for key, value in tags.items():
            try:
                audio[key] = value
            except (KeyError, mutagen.MutagenError):
                click.echo(f"  Skipping unsupported tag: {key}")
        audio.save()

        if cover_data:
            _embed_cover_art(file, cover_data)

        click.echo("\nTags written:")
        for key, value in tags.items():
            click.echo(f"  {key}: {value}")
        if cover_data:
            click.echo(f"  COVER ART: embedded ({len(cover_data)} bytes)")

        src = Path(file)
        safe_artist = _sanitize_filename(tags["artist"])
        safe_title = _sanitize_filename(tags["title"])
        new_name = f"{safe_artist} - {safe_title}{src.suffix}"
        dest = src.parent / new_name
        if dest != src:
            dest.write_bytes(src.read_bytes())
            if move:
                src.unlink()
                click.echo(f"\nMoved to: {dest}")
            else:
                click.echo(f"\nCopied to: {dest}")

    asyncio.run(_run())


def _sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    return name.strip(". ")


if __name__ == "__main__":
    cli()
