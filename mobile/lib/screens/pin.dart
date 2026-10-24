import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../l10n/l10n.dart';
import '../state/lock.dart';
import '../state/session.dart';
import '../state/settings.dart';
import '../ui/icons.dart';
import '../ui/theme.dart';
import '../ui/widgets.dart';

/// Four dots of a PIN.
class PinDots extends StatelessWidget {
  const PinDots(this.filled, {super.key, this.error = false});
  final int filled;
  final bool error;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final c = error ? oe.red : oe.primary;
    return Semantics(
      label: '$filled / 4',
      child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
        for (var i = 0; i < 4; i++)
          AnimatedContainer(
            duration: context.motion(150),
            width: 16,
            height: 16,
            margin: const EdgeInsets.symmetric(horizontal: 10),
            decoration: BoxDecoration(
                color: i < filled ? c : Colors.transparent, shape: BoxShape.circle, border: Border.all(color: c, width: 2)),
          ),
      ]),
    );
  }
}

/// Round PIN keypad (13a/13c). [leading] is the biometric key when available.
class PinPad extends StatelessWidget {
  const PinPad({super.key, required this.onDigit, required this.onBack, this.leading});
  final ValueChanged<String> onDigit;
  final VoidCallback onBack;
  final Widget? leading;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    Widget key(String d) => Semantics(
          button: true,
          label: d,
          child: Material(
            color: OeStyle.ios ? oe.fill : oe.m3nav,
            shape: const CircleBorder(),
            child: InkWell(
              key: Key('pin-$d'),
              customBorder: const CircleBorder(),
              onTap: () {
                HapticFeedback.lightImpact();
                onDigit(d);
              },
              child: SizedBox(width: 76, height: 76, child: Center(child: Text(d, style: display(28, color: oe.ink, weight: FontWeight.w500)))),
            ),
          ),
        );
    final back = Semantics(
      button: true,
      label: context.t.erase,
      child: InkResponse(
        onTap: onBack,
        child: SizedBox(width: 76, height: 76, child: Center(child: OeIcon('arrow-l', size: 30, color: oe.tint))),
      ),
    );
    return Column(mainAxisSize: MainAxisSize.min, children: [
      for (final row in [
        ['1', '2', '3'],
        ['4', '5', '6'],
        ['7', '8', '9'],
      ])
        Padding(
          padding: const EdgeInsets.only(bottom: 16),
          child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            for (var i = 0; i < 3; i++) ...[if (i > 0) const SizedBox(width: 28), key(row[i])],
          ]),
        ),
      Row(mainAxisAlignment: MainAxisAlignment.center, children: [
        SizedBox(width: 76, height: 76, child: leading),
        const SizedBox(width: 28),
        key('0'),
        const SizedBox(width: 28),
        back,
      ]),
    ]);
  }
}

/// 13a — create (and repeat) a 4-digit PIN; simple combinations are refused. Optional: can be skipped.
class PinSetupScreen extends StatefulWidget {
  const PinSetupScreen({super.key, this.change = false});
  final bool change;

  @override
  State<PinSetupScreen> createState() => _PinSetupScreenState();
}

class _PinSetupScreenState extends State<PinSetupScreen> {
  String _pin = '';
  String? _first;
  String? _error;

  Future<void> _digit(String d) async {
    if (_pin.length >= 4) return;
    setState(() {
      _pin += d;
      _error = null;
    });
    if (_pin.length < 4) return;
    final t = context.t;
    if (_first == null) {
      if (LockController.weak(_pin)) {
        setState(() {
          _error = t.pinWeak;
          _pin = '';
        });
        return;
      }
      setState(() {
        _first = _pin;
        _pin = '';
      });
      return;
    }
    if (_pin != _first) {
      setState(() {
        _error = t.pinMismatch;
        _pin = '';
        _first = null;
      });
      return;
    }
    final lock = context.read<LockController>();
    await lock.setPin(_pin);
    if (!mounted) return;
    if (widget.change) {
      toast(context, t.pinChanged);
      context.pop();
    } else if (await lock.biometricsAvailable()) {
      if (mounted) context.go('/pin/bio');
    } else {
      if (mounted) context.read<Session>().pinOffered();
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    return Scaffold(
      appBar: widget.change ? NavBar(backLabel: t.security) : null,
      body: SafeArea(
        child: Column(children: [
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(28, 24, 28, 0),
              child: Column(children: [
                const _BigIcon('lock'),
                const SizedBox(height: 14),
                Semantics(
                    header: true,
                    child: Text(_first == null ? t.pinCreate : t.pinRepeat,
                        textAlign: TextAlign.center, style: display(22, color: oe.brandInk, height: 1.25))),
                const SizedBox(height: 10),
                Text(t.pinCreateText, textAlign: TextAlign.center, style: TextStyle(color: oe.muted)),
                const SizedBox(height: 24),
                PinDots(_pin.length, error: _error != null),
                const SizedBox(height: 12),
                Text(_error ?? t.pinHint,
                    textAlign: TextAlign.center, style: TextStyle(fontSize: 12, color: _error != null ? oe.red : oe.muted)),
              ]),
            ),
          ),
          PinPad(onDigit: _digit, onBack: () => setState(() => _pin = _pin.isEmpty ? '' : _pin.substring(0, _pin.length - 1))),
          if (!widget.change)
            TextButton(
                onPressed: () => context.read<Session>().pinOffered(),
                child: Text(t.notNow, style: TextStyle(color: oe.tint, fontWeight: FontWeight.w600))),
          const SizedBox(height: 16),
        ]),
      ),
    );
  }
}

class _BigIcon extends StatelessWidget {
  const _BigIcon(this.icon);
  final String icon;

  @override
  Widget build(BuildContext context) => Container(
        width: 88,
        height: 88,
        alignment: Alignment.center,
        decoration: BoxDecoration(color: context.oe.navy100, borderRadius: BorderRadius.circular(28)),
        child: OeIcon(icon, size: 44, color: context.oe.tint, duo: .2),
      );
}

/// 13b — offer Face ID / fingerprint; refusing changes nothing.
class BiometricOfferScreen extends StatelessWidget {
  const BiometricOfferScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final ios = OeStyle.ios;
    Future<void> enable() async {
      final lock = context.read<LockController>();
      final settings = context.read<Settings>();
      final session = context.read<Session>();
      if (await lock.authenticate(t.bioReason)) settings.biometrics = true;
      session.pinOffered();
    }

    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(28, 24, 28, 24),
          child: Column(children: [
            _BigIcon(ios ? 'faceid' : 'finger'),
            const SizedBox(height: 14),
            Text(ios ? t.bioTitleIos : t.bioTitleAndroid, textAlign: TextAlign.center, style: display(22, color: oe.brandInk, height: 1.25)),
            const SizedBox(height: 10),
            Text(t.bioText, textAlign: TextAlign.center, style: TextStyle(color: oe.muted)),
            const Spacer(),
            OeButton(ios ? t.bioEnableIos : t.bioEnableAndroid, onPressed: enable),
            const SizedBox(height: 8),
            TextButton(
                onPressed: () => context.read<Session>().pinOffered(),
                child: Text(t.notNow, style: TextStyle(color: oe.tint, fontWeight: FontWeight.w600))),
          ]),
        ),
      ),
    );
  }
}

/// 13c — PIN on reopen and after auto-lock; biometric key on the left; after 5 errors a new WhatsApp code is needed.
class LockScreen extends StatefulWidget {
  const LockScreen({super.key});

  @override
  State<LockScreen> createState() => _LockScreenState();
}

class _LockScreenState extends State<LockScreen> {
  String _pin = '';
  bool _error = false;
  bool _bio = false;

  @override
  void initState() {
    super.initState();
    final lock = context.read<LockController>();
    if (lock.biometricsOn) {
      lock.biometricsAvailable().then((ok) {
        if (!mounted || !ok) return;
        setState(() => _bio = true);
        _useBio();
      });
    }
  }

  Future<void> _useBio() => context.read<LockController>().authenticate(context.t.bioReason);

  Future<void> _digit(String d) async {
    if (_pin.length >= 4) return;
    setState(() {
      _pin += d;
      _error = false;
    });
    if (_pin.length < 4) return;
    final ok = await context.read<LockController>().verify(_pin);
    if (!mounted) return;
    if (!ok) {
      HapticFeedback.heavyImpact();
      setState(() {
        _error = true;
        _pin = '';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final s = context.watch<Session>();
    final lock = context.watch<LockController>();
    final name = s.me?.fullName ?? '';
    final left = LockController.maxFailures - lock.failures;
    return Scaffold(
      body: SafeArea(
        child: Column(children: [
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(28, 24, 28, 0),
              child: Column(children: [
                Avatar(name, size: 72),
                const SizedBox(height: 14),
                Text(t.pinEnter(name.split(' ').first), textAlign: TextAlign.center, style: display(22, color: oe.brandInk)),
                const SizedBox(height: 20),
                PinDots(_pin.length, error: _error),
                const SizedBox(height: 14),
                if (_error) Text(t.pinWrong(left), style: TextStyle(color: oe.red, fontSize: 13)),
                TextButton(
                  onPressed: () => context.read<Session>().signOut(),
                  child: Text(t.pinForgot, style: TextStyle(color: oe.tint, fontWeight: FontWeight.w600, fontSize: 14)),
                ),
              ]),
            ),
          ),
          PinPad(
            onDigit: _digit,
            onBack: () => setState(() => _pin = _pin.isEmpty ? '' : _pin.substring(0, _pin.length - 1)),
            leading: _bio
                ? Semantics(
                    button: true,
                    label: t.bioUse,
                    child: InkResponse(
                        onTap: _useBio, child: Center(child: OeIcon(OeStyle.ios ? 'faceid' : 'finger', size: 32, color: oe.tint))),
                  )
                : null,
          ),
          const SizedBox(height: 32),
        ]),
      ),
    );
  }
}
