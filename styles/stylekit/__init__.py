"""Shared pieces for the three styles (Fast Cut, Talking Head Classic, Hands-On Classic) and the cover maker.

    paths   where things are: the kit, settings, shoots, Raw clips, work and cache folders, safe output names
    media   ffmpeg helpers: probe, crops, graded footage clips, stills, a frame reader, sound, the subject finder
    draw    Pillow drawing: easing, fonts, 2x antialiased shapes, 3D cards, pills, contact sheets
    words   transcripts (<clip>.words.txt), caption chunks, cut points that never clip a word
    audio   sound runs with crossfades at cuts, voice clean-up, music bed, loudness
    record  build records (library/buildrecord.py), written after a render
    fxhook  the effects library (effects/fx.py), put on a picture before its captions

A script in styles/<style>/ adds the styles folder to sys.path and imports these:

    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from stylekit import paths, media, draw, words
"""
