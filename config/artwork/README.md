# Artwork Directory

This directory contains artwork files for radio shows. These images are embedded into the MP3 files as album artwork.

## Supported Formats

- **JPEG** (.jpg, .jpeg) - Recommended
- **PNG** (.png) - Supported

## Recommendations

- **Resolution**: 500x500 to 1000x1000 pixels (square aspect ratio preferred)
- **File Size**: Keep under 1MB for faster processing
- **Quality**: High quality for best results in media players
- **Naming**: Use descriptive names matching your show keys

## Example Files

Place your artwork files here and reference them in `config_shows.json`:

```
config/artwork/
├── super-sonido.jpg
├── morning-jazz.png
├── weekend-classics.jpg
├── local-news.jpg
└── indie-spotlight.jpg
```

## Docker Volume Mapping

When running in Docker, map this directory as a read-only volume:

```yaml
volumes:
  - ./config/artwork:/config/artwork:ro
```

## File Permissions

Ensure artwork files are readable by the container user (UID 10001):

```bash
chmod 644 config/artwork/*.jpg
chmod 644 config/artwork/*.png
```