import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/oe_api.dart';
import '../l10n/l10n.dart';
import '../util/attach.dart';
import 'widgets.dart';
import 'icons.dart';
import 'theme.dart';

String absUrl(BuildContext context, String url) => context.read<OeApi>().client.absolute(url);

Future<void> openUrl(BuildContext context, String url) =>
    launchUrl(Uri.parse(absUrl(context, url)), mode: LaunchMode.externalApplication);

bool isImageName(String? name) => name != null && RegExp(r'\.(jpe?g|png|webp|gif)$', caseSensitive: false).hasMatch(name);
bool isAudioName(String? name) => name != null && RegExp(r'\.(m4a|mp3|ogg|webm|aac)$', caseSensitive: false).hasMatch(name);

/// Signed file links end with the stored key, which keeps the extension.
String? extOfUrl(String? url) {
  if (url == null) return null;
  final p = Uri.tryParse(url)?.path ?? url;
  return p.contains('.') ? p.substring(p.lastIndexOf('.')) : null;
}

/// Voice note bubble: play/pause, waveform, duration (design 5b).
class VoicePlayer extends StatefulWidget {
  const VoicePlayer({super.key, required this.url, this.onDark = false});
  final String url;
  final bool onDark;

  @override
  State<VoicePlayer> createState() => _VoicePlayerState();
}

class _VoicePlayerState extends State<VoicePlayer> {
  final _p = AudioPlayer();
  final List<StreamSubscription<dynamic>> _subs = [];
  Duration _pos = Duration.zero;
  Duration _len = Duration.zero;
  bool _playing = false;

  @override
  void initState() {
    super.initState();
    _subs.add(_p.onPositionChanged.listen((d) => setState(() => _pos = d)));
    _subs.add(_p.onDurationChanged.listen((d) => setState(() => _len = d)));
    _subs.add(_p.onPlayerStateChanged.listen((s) => setState(() => _playing = s == PlayerState.playing)));
    _subs.add(_p.onPlayerComplete.listen((_) => setState(() => _pos = Duration.zero)));
  }

  @override
  void dispose() {
    for (final s in _subs) {
      s.cancel();
    }
    _p.dispose();
    super.dispose();
  }

  Future<void> _toggle() async {
    try {
      if (_playing) {
        await _p.pause();
      } else {
        await _p.play(UrlSource(absUrl(context, widget.url)));
      }
    } catch (_) {
      if (mounted) await openUrl(context, widget.url);
    }
  }

  String _fmt(Duration d) => '${d.inMinutes}:${(d.inSeconds % 60).toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final fg = widget.onDark ? oe.onPrimary : oe.tint;
    final progress = _len.inMilliseconds == 0 ? 0.0 : _pos.inMilliseconds / _len.inMilliseconds;
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Semantics(
        button: true,
        label: _playing ? context.t.pause : context.t.play,
        child: GestureDetector(
          onTap: _toggle,
          child: Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(color: widget.onDark ? oe.onPrimary : oe.primary, shape: BoxShape.circle),
            alignment: Alignment.center,
            child: _playing
                ? Icon(Icons.pause_rounded, size: 20, color: widget.onDark ? oe.primary : oe.onPrimary)
                : OeIcon('play', size: 18, color: widget.onDark ? oe.primary : oe.onPrimary),
          ),
        ),
      ),
      const SizedBox(width: 10),
      SizedBox(width: 120, height: 28, child: Waveform(progress: progress, color: fg, seed: widget.url.hashCode)),
      const SizedBox(width: 10),
      Text(_fmt(_playing || _pos > Duration.zero ? _pos : _len),
          style: TextStyle(fontSize: 12, color: widget.onDark ? oe.onHero2 : oe.muted, fontFeatures: const [FontFeature.tabularFigures()])),
    ]);
  }
}

/// Decorative waveform bars (the design's `.wave`); the played part is solid.
class Waveform extends StatelessWidget {
  const Waveform({super.key, required this.progress, required this.color, this.seed = 7, this.bars = 28});
  final double progress;
  final Color color;
  final int seed;
  final int bars;

  @override
  Widget build(BuildContext context) => CustomPaint(painter: _WavePainter(progress, color, seed, bars));
}

class _WavePainter extends CustomPainter {
  _WavePainter(this.progress, this.color, this.seed, this.bars);
  final double progress;
  final Color color;
  final int seed;
  final int bars;

  @override
  void paint(Canvas canvas, Size size) {
    var s = seed.abs() % 233280 + 7;
    double rnd() {
      s = (s * 9301 + 49297) % 233280;
      return s / 233280;
    }

    final w = size.width / bars;
    for (var i = 0; i < bars; i++) {
      final v = .2 + (((i * .7).remainder(3.14)).abs() / 3.14) * .5 + rnd() * .3;
      final h = size.height * v.clamp(.15, 1);
      final played = i / bars < progress;
      final p = Paint()..color = color.withValues(alpha: played ? 1 : .55);
      canvas.drawRRect(
          RRect.fromRectAndRadius(Rect.fromLTWH(i * w + w * .2, (size.height - h) / 2, w * .55, h), const Radius.circular(2)), p);
    }
  }

  @override
  bool shouldRepaint(_WavePainter old) => old.progress != progress || old.color != color;
}

/// File row (`.att`): icon, name, open on tap.
class FileTile extends StatelessWidget {
  const FileTile({super.key, required this.name, this.url, this.subtitle, this.onRemove, this.onDark = false});
  final String name;
  final String? url;
  final String? subtitle;
  final VoidCallback? onRemove;
  final bool onDark;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    return InkWell(
      borderRadius: BorderRadius.circular(14),
      onTap: url == null ? null : () => openUrl(context, url!),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: onDark ? const Color(0x1FFFFFFF) : oe.surface,
          borderRadius: BorderRadius.circular(14),
          border: onDark ? null : Border.all(color: oe.line),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          OeIcon('file', size: 22, color: onDark ? oe.onPrimary : oe.red),
          const SizedBox(width: 10),
          Flexible(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
              Text(name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: onDark ? oe.onPrimary : oe.ink)),
              if (subtitle != null) Text(subtitle!, style: TextStyle(fontSize: 12, color: onDark ? oe.onHero2 : oe.muted)),
            ]),
          ),
          if (onRemove != null)
            IconButton(onPressed: onRemove, tooltip: context.t.remove, icon: OeIcon('x', size: 20, color: oe.muted))
          else if (url != null) ...[const SizedBox(width: 6), OeIcon('chev-r', size: 18, color: onDark ? oe.onHero2 : oe.muted)],
        ]),
      ),
    );
  }
}

/// Image from a signed link, tap to open full screen.
class NetImage extends StatelessWidget {
  const NetImage({super.key, required this.url, this.width = 200, this.height = 140});
  final String url;
  final double width;
  final double height;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final src = absUrl(context, url);
    return GestureDetector(
      onTap: () => Navigator.of(context, rootNavigator: true).push(MaterialPageRoute<void>(
        builder: (c) => Scaffold(
          backgroundColor: Colors.black,
          appBar: AppBar(backgroundColor: Colors.black, foregroundColor: Colors.white),
          body: Center(child: InteractiveViewer(child: Image.network(src))),
        ),
      )),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: Image.network(
          src,
          width: width,
          height: height,
          fit: BoxFit.cover,
          errorBuilder: (_, _, _) => Container(
            width: width,
            height: height,
            color: oe.navy100,
            alignment: Alignment.center,
            child: OeIcon('image', size: 32, color: oe.tint),
          ),
        ),
      ),
    );
  }
}

/// Media of a server file by its link: image, voice note or a file row.
class Attachment extends StatelessWidget {
  const Attachment({super.key, required this.url, this.name, this.kind, this.onDark = false});
  final String url;
  final String? name;
  final String? kind;
  final bool onDark;

  @override
  Widget build(BuildContext context) {
    final ext = extOfUrl(url);
    if (kind == 'image' || isImageName(name) || isImageName(ext)) return NetImage(url: url);
    if (kind == 'voice' || isAudioName(name) || isAudioName(ext)) return VoicePlayer(url: url, onDark: onDark);
    return FileTile(name: name ?? context.t.file, url: url, onDark: onDark);
  }
}

/// Camera or gallery, as an action sheet.
Future<Picked?> choosePhoto(BuildContext context) async {
  final t = context.t;
  final camera = await pickAction<bool>(context, options: [(true, t.camera, 'camera'), (false, t.gallery, 'image')]);
  if (camera == null) return null;
  return pickPhoto(camera: camera);
}
