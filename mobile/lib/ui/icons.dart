import 'package:flutter/widgets.dart';
import 'package:flutter_svg/flutter_svg.dart';

import 'icon_data.dart';
import 'theme.dart';

String _hex(Color c) {
  int ch(double v) => (v * 255).round().clamp(0, 255);
  return '#${[ch(c.r), ch(c.g), ch(c.b)].map((v) => v.toRadixString(16).padLeft(2, '0')).join()}';
}

/// An icon from the approved sprite (docs/design/mobile.html): 1.75 stroke, round caps, optional duotone fill.
class OeIcon extends StatelessWidget {
  const OeIcon(this.name, {super.key, this.size = 24, this.color, this.duo = 0, this.strokeWidth = 1.75, this.semanticLabel});

  final String name;
  final double size;
  final Color? color;

  /// Opacity of the soft fill layer: 0 normally, .18–.22 for the active tab (as in the design).
  final double duo;
  final double strokeWidth;
  final String? semanticLabel;

  static final Map<String, String> _cache = {};

  static bool exists(String name) => kIconData.containsKey(name);

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final col = color ?? IconTheme.of(context).color ?? oe.ink;
    final data = kIconData[name] ?? kIconData['alert']!;
    final key = '$name|${col.toARGB32()}|$duo|$strokeWidth|${oe.paper.toARGB32()}';
    final svg = _cache[key] ??= _build(data, col, oe);
    final pic = SvgPicture.string(svg, width: size, height: size, excludeFromSemantics: semanticLabel == null,
        semanticsLabel: semanticLabel);
    return SizedBox(width: size, height: size, child: pic);
  }

  String _build((String, String) data, Color col, OeColors oe) {
    final c = _hex(col);
    var inner = data.$2.replaceAll('#C0', c).replaceAll('#DUO', '${col.a * duo}');
    inner = inner.replaceAll('#RED', _hex(oe.red)).replaceAll('#LOGOE', _hex(oe.logoE)).replaceAll('#PAPER', _hex(oe.paper));
    final op = col.a < 1 ? ' stroke-opacity="${col.a}"' : '';
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="${data.$1}" fill="none" stroke="$c"$op '
        'stroke-width="$strokeWidth" stroke-linecap="round" stroke-linejoin="round">$inner</svg>';
  }
}

/// The 1E mark in brand colours.
class OeLogoMark extends StatelessWidget {
  const OeLogoMark({super.key, this.width = 44});
  final double width;

  @override
  Widget build(BuildContext context) => SizedBox(
        width: width,
        height: width * 48 / 60,
        child: FittedBox(child: OeIcon('logo', size: width, strokeWidth: 0)),
      );
}

/// Icon names a shop item may carry (`icon` field), mapped onto the sprite.
String shopIcon(String? name) {
  const alias = {'pen': 'pencil', 'shirt': 'gift', 'tshirt': 'gift', 'books': 'book', 'notebook': 'notebook', 'cup': 'trophy'};
  final n = alias[name] ?? name;
  return n != null && OeIcon.exists(n) ? n : 'gift';
}
