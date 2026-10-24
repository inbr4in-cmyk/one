import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';

import '../api/api_client.dart';
import '../l10n/l10n.dart';
import 'icons.dart';
import 'theme.dart';

// ---------------------------------------------------------------- basics

class OeCard extends StatelessWidget {
  const OeCard({super.key, required this.child, this.padding = const EdgeInsets.all(16), this.onTap, this.border, this.color});
  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;
  final Color? border;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final r = BorderRadius.circular(OeStyle.cardRadius);
    final ios = OeStyle.ios;
    final box = Container(
      decoration: BoxDecoration(
        color: color ?? oe.surface,
        borderRadius: r,
        border: border != null
            ? Border.all(color: border!, width: 2)
            : (ios ? Border.all(color: oe.line) : null),
        boxShadow: ios || border != null ? null : const [BoxShadow(color: Color(0x0F0F1A33), blurRadius: 2, offset: Offset(0, 1))],
      ),
      child: Padding(padding: padding, child: child),
    );
    if (onTap == null) return box;
    return Material(color: Colors.transparent, borderRadius: r, child: InkWell(borderRadius: r, onTap: onTap, child: box));
  }
}

/// A list card whose rows are separated by hairlines (`.list .li`).
class OeList extends StatelessWidget {
  const OeList({super.key, required this.children});
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final rows = <Widget>[];
    for (var i = 0; i < children.length; i++) {
      if (i > 0) rows.add(Divider(height: 1, thickness: 1, color: oe.line));
      rows.add(children[i]);
    }
    return Container(
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: oe.surface,
        borderRadius: BorderRadius.circular(OeStyle.cardRadius),
        border: OeStyle.ios ? Border.all(color: oe.line) : null,
        boxShadow: OeStyle.ios ? null : const [BoxShadow(color: Color(0x0F0F1A33), blurRadius: 2, offset: Offset(0, 1))],
      ),
      child: Column(mainAxisSize: MainAxisSize.min, children: rows),
    );
  }
}

class OeRow extends StatelessWidget {
  const OeRow({super.key, this.leading, required this.title, this.subtitle, this.trailing, this.onTap, this.chevron = false,
      this.padding = const EdgeInsets.symmetric(horizontal: 14, vertical: 12), this.titleStyle});
  final Widget? leading;
  final String title;
  final String? subtitle;
  final Widget? trailing;
  final VoidCallback? onTap;
  final bool chevron;
  final EdgeInsetsGeometry padding;
  final TextStyle? titleStyle;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final body = Padding(
      padding: padding,
      child: Row(children: [
        if (leading != null) ...[leading!, const SizedBox(width: 12)],
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
            Text(title, style: titleStyle ?? const TextStyle(fontSize: 15, fontWeight: FontWeight.w500)),
            if (subtitle != null && subtitle!.isNotEmpty)
              Padding(padding: const EdgeInsets.only(top: 2), child: Text(subtitle!, style: TextStyle(fontSize: 12.5, color: oe.muted))),
          ]),
        ),
        if (trailing != null) ...[const SizedBox(width: 8), trailing!],
        if (chevron) ...[const SizedBox(width: 4), OeIcon('chev-r', size: 20, color: oe.muted)],
      ]),
    );
    if (onTap == null) return body;
    return InkWell(onTap: onTap, child: body);
  }
}

/// Rounded square icon tile used in list rows (`.lic`).
class IconTile extends StatelessWidget {
  const IconTile(this.icon, {super.key, this.bg, this.fg, this.size = 32, this.radius = 9});
  final String icon;
  final Color? bg;
  final Color? fg;
  final double size;
  final double radius;

  @override
  Widget build(BuildContext context) => Container(
        width: size,
        height: size,
        alignment: Alignment.center,
        decoration: BoxDecoration(color: bg ?? context.oe.navy100, borderRadius: BorderRadius.circular(radius)),
        child: OeIcon(icon, size: size * .6, color: fg ?? context.oe.tint),
      );
}

enum Tone { ok, warn, info, red, mut }

class Pill extends StatelessWidget {
  const Pill(this.text, {super.key, this.tone = Tone.mut, this.icon});
  final String text;
  final Tone tone;
  final String? icon;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final (bg, fg) = switch (tone) {
      Tone.ok => (oe.ok100, oe.ok),
      Tone.warn => (oe.warn100, oe.warn),
      Tone.info => (oe.info100, oe.info),
      Tone.red => (oe.red100, oe.red),
      Tone.mut => (oe.fill, oe.muted),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(999)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        if (icon != null) ...[OeIcon(icon!, size: 13, color: fg, strokeWidth: 2.2), const SizedBox(width: 4)],
        Text(text, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: fg)),
      ]),
    );
  }
}

/// Filter chip (`.chip`): iOS filled, Android outlined M3.
class OeChip extends StatelessWidget {
  const OeChip(this.label, {super.key, this.selected = false, this.onTap});
  final String label;
  final bool selected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final ios = OeStyle.ios;
    final bg = selected ? (ios ? oe.primary : oe.navy100) : (ios ? oe.chip : Colors.transparent);
    final fg = selected && ios ? oe.onPrimary : oe.ink;
    return Semantics(
      selected: selected,
      button: true,
      child: GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: context.motion(150),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
          decoration: BoxDecoration(
            color: bg,
            borderRadius: BorderRadius.circular(ios ? 999 : 8),
            border: !ios && !selected ? Border.all(color: oe.line) : null,
          ),
          child: Text(label, style: TextStyle(fontSize: 13, fontWeight: FontWeight.w500, color: fg)),
        ),
      ),
    );
  }
}

enum BtnKind { primary, red, tonal, ghost }

class OeButton extends StatelessWidget {
  const OeButton(this.label, {super.key, this.onPressed, this.kind = BtnKind.primary, this.small = false, this.loading = false,
      this.icon, this.expand = true});
  final String label;
  final VoidCallback? onPressed;
  final BtnKind kind;
  final bool small;
  final bool loading;
  final String? icon;
  final bool expand;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final (bg, fg) = switch (kind) {
      BtnKind.primary => (oe.primary, oe.onPrimary),
      BtnKind.red => (oe.red, OeColors.white),
      BtnKind.tonal => (oe.navy100, oe.brandInk),
      BtnKind.ghost => (Colors.transparent, oe.tint),
    };
    final disabled = onPressed == null || loading;
    final h = small ? 36.0 : 52.0;
    final child = loading
        ? SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2.2, color: fg))
        : Row(mainAxisSize: MainAxisSize.min, children: [
            if (icon != null) ...[OeIcon(icon!, size: small ? 16 : 20, color: fg), const SizedBox(width: 8)],
            Flexible(
                child: Text(label,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: small ? 14 : 16, fontWeight: FontWeight.w600, color: fg))),
          ]);
    return Semantics(
      button: true,
      enabled: !disabled,
      child: Opacity(
        opacity: onPressed == null ? .45 : 1,
        child: Material(
          color: bg,
          borderRadius: BorderRadius.circular(OeStyle.btnRadius),
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: disabled ? null : onPressed,
            child: SizedBox(
              height: h,
              width: expand ? double.infinity : null,
              child: Padding(
                padding: EdgeInsets.symmetric(horizontal: small ? 14 : 20),
                child: Center(widthFactor: 1, child: child),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class Avatar extends StatelessWidget {
  const Avatar(this.name, {super.key, this.size = 44, this.online = false, this.tone});
  final String name;
  final double size;
  final bool online;
  final int? tone;

  static String initials(String name) {
    final parts = name.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
    if (parts.isEmpty) return '·';
    if (parts.length == 1) return parts.first.characters.first.toUpperCase();
    return (parts[0].characters.first + parts[1].characters.first).toUpperCase();
  }

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final i = (tone ?? name.codeUnits.fold<int>(0, (a, b) => a + b)) % 5;
    final pairs = [(oe.navy100, oe.tint), (oe.ok100, oe.ok), (oe.warn100, oe.warn), (oe.info100, oe.info), (oe.red100, oe.red)];
    final (bg, fg) = pairs[i];
    return SizedBox(
      width: size,
      height: size,
      child: Stack(clipBehavior: Clip.none, children: [
        Container(
          width: size,
          height: size,
          alignment: Alignment.center,
          decoration: BoxDecoration(color: bg, shape: BoxShape.circle),
          child: Text(initials(name), style: TextStyle(color: fg, fontWeight: FontWeight.w600, fontSize: size * .34)),
        ),
        if (online)
          Positioned(
            right: 0,
            bottom: 0,
            child: Container(
              width: 12,
              height: 12,
              decoration: BoxDecoration(color: oe.ok, shape: BoxShape.circle, border: Border.all(color: oe.paper, width: 2)),
            ),
          ),
      ]),
    );
  }
}

class Coin extends StatelessWidget {
  const Coin({super.key, this.size = 20});
  final double size;

  @override
  Widget build(BuildContext context) => Container(
        width: size,
        height: size,
        alignment: Alignment.center,
        decoration: BoxDecoration(color: context.oe.coin, shape: BoxShape.circle),
        child: OeIcon('c1', size: size * .68, color: OeColors.white, strokeWidth: 2.2),
      );
}

class CountBadge extends StatelessWidget {
  const CountBadge(this.n, {super.key, this.size = 22});
  final int n;
  final double size;

  @override
  Widget build(BuildContext context) => Container(
        constraints: BoxConstraints(minWidth: size),
        height: size,
        padding: const EdgeInsets.symmetric(horizontal: 6),
        alignment: Alignment.center,
        decoration: BoxDecoration(color: context.oe.red, borderRadius: BorderRadius.circular(size / 2)),
        child: Text(n > 99 ? '99+' : '$n',
            style: TextStyle(color: OeColors.white, fontSize: size * .52, fontWeight: FontWeight.w600)),
      );
}

/// Segmented control: iOS segmented / M3 segmented buttons.
class OeSegmented<T> extends StatelessWidget {
  const OeSegmented({super.key, required this.options, required this.value, required this.onChanged});
  final List<(T, String)> options;
  final T value;
  final ValueChanged<T> onChanged;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final ios = OeStyle.ios;
    return Container(
      padding: EdgeInsets.all(ios ? 2 : 0),
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: ios ? oe.fill : null,
        borderRadius: BorderRadius.circular(ios ? 10 : 999),
        border: ios ? null : Border.all(color: oe.outline),
      ),
      child: Row(children: [
        for (var i = 0; i < options.length; i++)
          Expanded(
            child: Semantics(
              selected: options[i].$1 == value,
              button: true,
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () {
                  HapticFeedback.selectionClick();
                  onChanged(options[i].$1);
                },
                child: AnimatedContainer(
                  duration: context.motion(150),
                  height: ios ? 32 : 40,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: options[i].$1 == value ? (ios ? oe.surface : oe.navy100) : null,
                    borderRadius: ios ? BorderRadius.circular(8) : null,
                    border: !ios && i > 0 ? Border(left: BorderSide(color: oe.outline)) : null,
                    boxShadow: ios && options[i].$1 == value
                        ? const [BoxShadow(color: Color(0x240F1A33), blurRadius: 3, offset: Offset(0, 1))]
                        : null,
                  ),
                  child: Text(options[i].$2,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 13, fontWeight: ios ? FontWeight.w600 : FontWeight.w500, color: oe.ink)),
                ),
              ),
            ),
          ),
      ]),
    );
  }
}

class OeSwitch extends StatelessWidget {
  const OeSwitch({super.key, required this.value, required this.onChanged});
  final bool value;
  final ValueChanged<bool>? onChanged;

  @override
  Widget build(BuildContext context) => OeStyle.ios
      ? CupertinoSwitch(value: value, onChanged: onChanged, activeTrackColor: context.oe.ok)
      : Switch(value: value, onChanged: onChanged);
}

class SectionTitle extends StatelessWidget {
  const SectionTitle(this.title, {super.key, this.action, this.onAction, this.padding = const EdgeInsets.only(top: 6, bottom: 10)});
  final String title;
  final String? action;
  final VoidCallback? onAction;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) => Padding(
        padding: padding,
        child: Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
          Expanded(child: Text(title, style: display(15, color: context.oe.brandInk))),
          if (action != null)
            GestureDetector(
              onTap: onAction,
              child: Text(action!, style: TextStyle(color: context.oe.tint, fontWeight: FontWeight.w600, fontSize: 14)),
            ),
        ]),
      );
}

/// Uppercase group label (`СЕГОДНЯ`, `АЙДАНА · PI-3`).
class Eyebrow extends StatelessWidget {
  const Eyebrow(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 12, bottom: 6),
        child: Text(text.toUpperCase(),
            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, letterSpacing: .8, color: context.oe.muted)),
      );
}

// ---------------------------------------------------------------- page chrome

/// Root tab page header: iOS large title with actions above, Android M3 top app bar.
class TabHeader extends StatelessWidget {
  const TabHeader(this.title, {super.key, this.actions = const []});
  final String title;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    if (OeStyle.ios) {
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(height: 40, child: Row(mainAxisAlignment: MainAxisAlignment.end, children: actions)),
          Semantics(
              header: true,
              child: Padding(
                  padding: const EdgeInsets.only(top: 2, bottom: 8),
                  child: Text(title, style: display(28, color: oe.brandInk)))),
        ]),
      );
    }
    return SizedBox(
      height: 64,
      child: Padding(
        padding: const EdgeInsets.only(left: 16, right: 4),
        child: Row(children: [
          Expanded(
              child: Semantics(
                  header: true,
                  child: Text(title, style: TextStyle(fontSize: 21, fontWeight: FontWeight.w500, color: oe.ink)))),
          ...actions,
        ]),
      ),
    );
  }
}

class HeaderAction extends StatelessWidget {
  const HeaderAction(this.icon, {super.key, required this.onTap, required this.label, this.badge = 0});
  final String icon;
  final VoidCallback onTap;
  final String label;
  final int badge;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    return Semantics(
      button: true,
      label: label,
      child: InkResponse(
        onTap: onTap,
        radius: 22,
        child: SizedBox(
          width: 44,
          height: 44,
          child: Stack(alignment: Alignment.center, clipBehavior: Clip.none, children: [
            OeIcon(icon, color: OeStyle.ios ? oe.tint : oe.ink),
            if (badge > 0)
              Positioned(
                  top: 9,
                  right: 9,
                  child: Container(width: 9, height: 9, decoration: BoxDecoration(color: oe.red, shape: BoxShape.circle))),
          ]),
        ),
      ),
    );
  }
}

/// Detail page navigation bar: iOS back chevron with label and centred title; Android back arrow and left title.
class NavBar extends StatelessWidget implements PreferredSizeWidget {
  const NavBar({super.key, this.title, this.subtitle, this.backLabel, this.actions = const [], this.onBack});
  final String? title;
  final String? subtitle;
  final String? backLabel;
  final List<Widget> actions;
  final VoidCallback? onBack;

  @override
  Size get preferredSize => Size.fromHeight(OeStyle.ios ? 46 : 64);

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final ios = OeStyle.ios;
    void back() {
      if (onBack != null) {
        onBack!();
      } else if (context.canPop()) {
        context.pop();
      } else {
        context.go('/home');
      }
    }

    final titleW = title == null
        ? const SizedBox()
        : Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: ios ? CrossAxisAlignment.center : CrossAxisAlignment.start,
            children: [
              Text(title!,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: ios ? 16 : 19, fontWeight: ios ? FontWeight.w600 : FontWeight.w500)),
              if (subtitle != null)
                Text(subtitle!, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 12, color: oe.muted)),
            ],
          );
    return SafeArea(
      bottom: false,
      child: SizedBox(
        height: preferredSize.height,
        child: ios
            ? Stack(children: [
                Positioned.fill(left: 90, right: 90, child: Center(child: Semantics(header: true, child: titleW))),
                Positioned.fill(child: Row(children: [
                  Semantics(
                    button: true,
                    label: backLabel ?? context.t.back,
                    child: GestureDetector(
                      onTap: back,
                      behavior: HitTestBehavior.opaque,
                      child: Padding(
                        padding: const EdgeInsets.only(left: 4, right: 8),
                        child: Row(children: [
                          OeIcon('chev-l', size: 28, color: oe.tint),
                          // Like UIKit: the back title gives way when the page title is long.
                          if (backLabel != null && (title == null || title!.length <= 16))
                            ConstrainedBox(
                              constraints: const BoxConstraints(maxWidth: 90),
                              child: Text(backLabel!, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 17, color: oe.tint)),
                            ),
                        ]),
                      ),
                    ),
                  ),
                  const Spacer(),
                  ...actions,
                  const SizedBox(width: 4),
                ])),
              ])
            : Row(children: [
                const SizedBox(width: 4),
                IconButton(onPressed: back, tooltip: context.t.back, icon: OeIcon('arrow-l', color: oe.ink)),
                Expanded(child: Semantics(header: true, child: titleW)),
                ...actions,
                const SizedBox(width: 4),
              ]),
      ),
    );
  }
}

/// Grey line under chat headers: «Переписка сохраняется и доступна администрации школы».
class NoticeBar extends StatelessWidget {
  const NoticeBar(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        color: context.oe.fill,
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          OeIcon('shield', size: 14, color: context.oe.muted, strokeWidth: 2),
          const SizedBox(width: 6),
          Flexible(
              child: Text(text,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.w500, color: context.oe.muted))),
        ]),
      );
}

class Banner2 extends StatelessWidget {
  const Banner2({super.key, required this.title, this.text, this.tone = Tone.info, this.icon = 'alert', this.action, this.onTap});
  final String title;
  final String? text;
  final Tone tone;
  final String icon;
  final Widget? action;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final (bg, fg) = switch (tone) {
      Tone.ok => (oe.ok100, oe.ok),
      Tone.warn => (oe.warn100, oe.warn),
      Tone.red => (oe.red100, oe.red),
      _ => (oe.info100, oe.info),
    };
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(14)),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Padding(padding: const EdgeInsets.only(top: 1), child: OeIcon(icon, size: 18, color: fg)),
          const SizedBox(width: 10),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title, style: TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600, color: fg)),
              if (text != null) Text(text!, style: TextStyle(fontSize: 13, color: oe.ink)),
              if (action != null) Padding(padding: const EdgeInsets.only(top: 8), child: action!),
            ]),
          ),
        ]),
      ),
    );
  }
}

// ---------------------------------------------------------------- states

class EmptyState extends StatelessWidget {
  const EmptyState({super.key, required this.icon, required this.title, this.text, this.action});
  final String icon;
  final String title;
  final String? text;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 36, horizontal: 24),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        Container(
          width: 72,
          height: 72,
          alignment: Alignment.center,
          decoration: BoxDecoration(color: oe.navy100, borderRadius: BorderRadius.circular(24)),
          child: OeIcon(icon, size: 34, color: oe.tint, duo: .2),
        ),
        const SizedBox(height: 14),
        Text(title, textAlign: TextAlign.center, style: display(16, color: oe.brandInk, height: 1.3)),
        if (text != null) ...[
          const SizedBox(height: 6),
          Text(text!, textAlign: TextAlign.center, style: TextStyle(color: oe.muted, fontSize: 14)),
        ],
        if (action != null) ...[const SizedBox(height: 16), action!],
      ]),
    );
  }
}

String errorText(BuildContext context, Object e) {
  if (e is ApiException) {
    if (e.isNetwork) return context.t.errNetwork;
    if (e.detail.isNotEmpty) return e.detail;
  }
  return context.t.errGeneric;
}

class ErrorState extends StatelessWidget {
  const ErrorState({super.key, required this.error, this.onRetry});
  final Object error;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) => EmptyState(
        icon: 'alert',
        title: errorText(context, error),
        action: onRetry == null ? null : OeButton(context.t.retry, kind: BtnKind.tonal, small: true, expand: false, onPressed: onRetry),
      );
}

class Skeleton extends StatelessWidget {
  const Skeleton({super.key, this.lines = 4});
  final int lines;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    return Semantics(
      label: context.t.loading,
      child: Column(children: [
        for (var i = 0; i < lines; i++)
          Container(
            height: i == 0 ? 84 : 56,
            margin: const EdgeInsets.only(bottom: 12),
            decoration: BoxDecoration(color: oe.fill, borderRadius: BorderRadius.circular(OeStyle.cardRadius)),
          ),
      ]),
    );
  }
}

/// Loads data with a skeleton, shows server errors with retry, and supports pull-to-refresh.
class Loader<T> extends StatefulWidget {
  const Loader({super.key, required this.load, required this.builder, this.skeletonLines = 4});
  final Future<T> Function() load;
  final Widget Function(BuildContext context, T data, Future<void> Function() reload) builder;
  final int skeletonLines;

  @override
  State<Loader<T>> createState() => _LoaderState<T>();
}

class _LoaderState<T> extends State<Loader<T>> {
  T? _data;
  Object? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _run();
  }

  @override
  void didUpdateWidget(covariant Loader<T> old) {
    super.didUpdateWidget(old);
    if (old.key != widget.key) _run();
  }

  Future<void> _run() async {
    setState(() {
      _loading = _data == null;
      _error = null;
    });
    try {
      final d = await widget.load();
      if (mounted) setState(() => _data = d);
    } catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading && _data == null) {
      return Padding(padding: const EdgeInsets.all(16), child: Skeleton(lines: widget.skeletonLines));
    }
    if (_error != null && _data == null) return ErrorState(error: _error!, onRetry: _run);
    return widget.builder(context, _data as T, _run);
  }
}

// ---------------------------------------------------------------- feedback

void toast(BuildContext context, String msg, {bool error = false}) {
  final m = ScaffoldMessenger.maybeOf(context);
  m?.hideCurrentSnackBar();
  m?.showSnackBar(SnackBar(
    content: Text(msg),
    backgroundColor: error ? context.oe.red : null,
    duration: const Duration(seconds: 3),
  ));
}

void toastError(BuildContext context, Object e) => toast(context, errorText(context, e), error: true);

Future<bool> confirm(BuildContext context, {required String title, String? text, required String ok, bool danger = false}) async {
  final t = context.t;
  final r = await showAdaptiveDialog<bool>(
    context: context,
    builder: (c) => AlertDialog.adaptive(
      title: Text(title),
      content: text == null ? null : Text(text),
      actions: [
        adaptiveAction(c, label: t.cancel, onPressed: () => Navigator.pop(c, false)),
        adaptiveAction(c, label: ok, onPressed: () => Navigator.pop(c, true), danger: danger, primary: true),
      ],
    ),
  );
  return r ?? false;
}

Widget adaptiveAction(BuildContext context, {required String label, required VoidCallback onPressed, bool danger = false, bool primary = false}) {
  if (OeStyle.ios) {
    return CupertinoDialogAction(onPressed: onPressed, isDestructiveAction: danger, isDefaultAction: primary, child: Text(label));
  }
  return TextButton(
      onPressed: onPressed,
      child: Text(label, style: TextStyle(color: danger ? context.oe.red : context.oe.tint, fontWeight: FontWeight.w600)));
}

/// iOS action sheet / Android M3 bottom sheet with options.
Future<T?> pickAction<T>(BuildContext context, {String? title, String? message, required List<(T, String, String?)> options}) {
  final oe = context.oe;
  if (OeStyle.ios) {
    return showCupertinoModalPopup<T>(
      context: context,
      builder: (c) => CupertinoActionSheet(
        title: title == null ? null : Text(title),
        message: message == null ? null : Text(message),
        actions: [
          for (final o in options)
            CupertinoActionSheetAction(
              onPressed: () => Navigator.pop(c, o.$1),
              child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                if (o.$3 != null) ...[OeIcon(o.$3!, color: oe.tint), const SizedBox(width: 10)],
                Text(o.$2),
              ]),
            ),
        ],
        cancelButton: CupertinoActionSheetAction(onPressed: () => Navigator.pop(c), isDefaultAction: true, child: Text(context.t.cancel)),
      ),
    );
  }
  return showModalBottomSheet<T>(
    context: context,
    showDragHandle: true,
    backgroundColor: oe.surface,
    builder: (c) => SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          if (title != null) Text(title, style: display(16, color: oe.brandInk)),
          if (message != null) Padding(padding: const EdgeInsets.only(top: 4), child: Text(message, style: TextStyle(color: oe.muted))),
          const SizedBox(height: 10),
          for (final o in options)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: InkWell(
                borderRadius: BorderRadius.circular(16),
                onTap: () => Navigator.pop(c, o.$1),
                child: Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(borderRadius: BorderRadius.circular(16), border: Border.all(color: oe.line)),
                  child: Row(children: [
                    if (o.$3 != null) ...[OeIcon(o.$3!, color: oe.tint), const SizedBox(width: 12)],
                    Expanded(child: Text(o.$2, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w500))),
                  ]),
                ),
              ),
            ),
        ]),
      ),
    ),
  );
}

/// Scrollable page body with the design's 16 px gutters and 12 px gaps.
class PageList extends StatelessWidget {
  const PageList({super.key, required this.children, this.onRefresh, this.padding = const EdgeInsets.fromLTRB(16, 4, 16, 24)});
  final List<Widget> children;
  final Future<void> Function()? onRefresh;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) {
    final list = ListView.separated(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: padding,
      itemCount: children.length,
      separatorBuilder: (_, _) => const SizedBox(height: 12),
      itemBuilder: (_, i) => children[i],
    );
    if (onRefresh == null) return list;
    return RefreshIndicator.adaptive(onRefresh: onRefresh!, child: list);
  }
}
