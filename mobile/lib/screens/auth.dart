import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../api/api_client.dart';
import '../config.dart';
import '../l10n/l10n.dart';
import '../state/session.dart';
import '../ui/icons.dart';
import '../ui/theme.dart';
import '../ui/widgets.dart';
import '../util/format.dart';

/// 1a — logo on warm paper while the session is restored.
class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    return Scaffold(
      body: Stack(children: [
        Center(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const OeLogoMark(width: 96),
            const SizedBox(height: 16),
            const Wordmark(size: 32),
            const SizedBox(height: 18),
            Row(mainAxisSize: MainAxisSize.min, children: [
              for (var i = 0; i < 3; i++)
                Container(
                  width: 7,
                  height: 7,
                  margin: const EdgeInsets.symmetric(horizontal: 3),
                  decoration: BoxDecoration(color: i == 0 ? oe.red : oe.line, shape: BoxShape.circle),
                ),
            ]),
          ]),
        ),
        Positioned(
          left: 0,
          right: 0,
          bottom: 56,
          child: Text(context.t.splashFoot, textAlign: TextAlign.center, style: TextStyle(fontSize: 13, color: oe.muted)),
        ),
      ]),
    );
  }
}

/// «ONE ENGLISH / INNOVATION IN LEARNING».
class Wordmark extends StatelessWidget {
  const Wordmark({super.key, this.size = 19});
  final double size;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final st = TextStyle(fontFamily: 'PlayfairDisplay', fontWeight: FontWeight.w800, fontSize: size, height: .95);
    return Column(mainAxisSize: MainAxisSize.min, children: [
      Text.rich(TextSpan(children: [
        TextSpan(text: 'ONE ', style: st.copyWith(color: oe.brandInk)),
        TextSpan(text: 'ENGLISH', style: st.copyWith(color: oe.red)),
      ])),
      SizedBox(height: size * .25),
      Text('INNOVATION IN LEARNING', style: TextStyle(fontSize: size * .31, letterSpacing: size * .1, color: oe.muted)),
    ]);
  }
}

class OfflineScreen extends StatelessWidget {
  const OfflineScreen({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
        body: SafeArea(
          child: Center(
            child: EmptyState(
              icon: 'alert',
              title: context.t.offlineTitle,
              text: context.t.offlineText,
              action: OeButton(context.t.retry, expand: false, onPressed: () => context.read<Session>().retryBoot()),
            ),
          ),
        ),
      );
}

/// 1b — phone number with a fixed +7 prefix; the code goes to WhatsApp.
class LoginPhoneScreen extends StatefulWidget {
  const LoginPhoneScreen({super.key});

  @override
  State<LoginPhoneScreen> createState() => _LoginPhoneScreenState();
}

class _LoginPhoneScreenState extends State<LoginPhoneScreen> {
  final _ctl = TextEditingController();
  bool _busy = false;
  String? _error;

  String get _digits => _ctl.text.replaceAll(RegExp(r'\D'), '');

  @override
  void dispose() {
    _ctl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final t = context.t;
    if (_digits.length != 10) {
      setState(() => _error = t.phoneInvalid);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    final phone = '+7$_digits';
    try {
      await context.read<Session>().requestCode(phone);
      if (mounted) context.push('/login/code', extra: phone);
    } catch (e) {
      if (mounted) setState(() => _error = errorText(context, e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final s = context.watch<Session>();
    final note = s.lockExpired ? t.pinTooMany : (s.staffRejected ? t.staffRejected : null);
    return Scaffold(
      body: SafeArea(
        child: ListView(padding: const EdgeInsets.fromLTRB(24, 12, 24, 24), children: [
          const Align(alignment: Alignment.centerLeft, child: OeLogoMark(width: 40)),
          const SizedBox(height: 20),
          Semantics(header: true, child: Text(t.loginTitle, style: display(24, color: oe.brandInk, height: 1.2))),
          const SizedBox(height: 12),
          Text(t.loginText, style: TextStyle(color: oe.muted, fontSize: 15)),
          if (note != null) ...[const SizedBox(height: 16), Banner2(title: note, tone: Tone.warn)],
          const SizedBox(height: 20),
          Text(t.phoneLabel, style: TextStyle(fontSize: 13, color: oe.muted, fontWeight: FontWeight.w500)),
          const SizedBox(height: 6),
          Container(
            height: 56,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            decoration: BoxDecoration(
              color: OeStyle.ios ? oe.surface : Colors.transparent,
              borderRadius: BorderRadius.circular(OeStyle.ios ? 14 : 4),
              border: Border.all(color: OeStyle.ios ? oe.line : oe.primary, width: OeStyle.ios ? 1 : 2),
            ),
            child: Row(children: [
              Text('+7', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w500, color: oe.muted)),
              Container(width: 1, height: 28, color: oe.line, margin: const EdgeInsets.symmetric(horizontal: 10)),
              Expanded(
                child: TextField(
                  key: const Key('phone'),
                  controller: _ctl,
                  autofocus: true,
                  keyboardType: TextInputType.phone,
                  autofillHints: const [AutofillHints.telephoneNumberNational],
                  textInputAction: TextInputAction.done,
                  onSubmitted: (_) => _submit(),
                  inputFormatters: [_PhoneMask()],
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.w500, letterSpacing: .4, color: oe.ink,
                      fontFeatures: const [FontFeature.tabularFigures()]),
                  decoration: const InputDecoration(
                      border: InputBorder.none, enabledBorder: InputBorder.none, focusedBorder: InputBorder.none,
                      filled: false, isDense: true, hintText: '700 000 00 00', contentPadding: EdgeInsets.zero),
                ),
              ),
            ]),
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(_error!, style: TextStyle(color: oe.red, fontSize: 13)),
            ),
          const SizedBox(height: 20),
          Text(t.codeChannel, style: TextStyle(fontSize: 13, color: oe.muted, fontWeight: FontWeight.w500)),
          const SizedBox(height: 6),
          Row(children: [
            Expanded(child: _Channel(icon: 'whatsapp-color', title: 'WhatsApp', text: t.waFast, on: true)),
            const SizedBox(width: 10),
            Expanded(child: _Channel(icon: 'chat', title: 'SMS', text: t.smsSoon, on: false)),
          ]),
          const SizedBox(height: 20),
          OeButton(t.getCode, loading: _busy, onPressed: _submit),
          const SizedBox(height: 20),
          Text(t.noNumber(AppConfig.schoolWhatsApp),
              textAlign: TextAlign.center, style: TextStyle(fontSize: 12, color: oe.muted)),
        ]),
      ),
    );
  }
}

class _Channel extends StatelessWidget {
  const _Channel({required this.icon, required this.title, required this.text, required this.on});
  final String icon;
  final String title;
  final String text;
  final bool on;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    return Opacity(
      opacity: on ? 1 : .55,
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: oe.surface,
          borderRadius: BorderRadius.circular(OeStyle.cardRadius),
          border: Border.all(color: on ? oe.primary : oe.line, width: on ? 2 : 1.5),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            OeIcon(icon, size: 22, color: oe.tint),
            const Spacer(),
            Container(
              width: 20,
              height: 20,
              alignment: Alignment.center,
              decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: on ? oe.primary : oe.outline, width: 2)),
              child: on ? Container(width: 10, height: 10, decoration: BoxDecoration(color: oe.primary, shape: BoxShape.circle)) : null,
            ),
          ]),
          const SizedBox(height: 6),
          Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
          Text(text, style: TextStyle(fontSize: 12, color: oe.muted)),
        ]),
      ),
    );
  }
}

class _PhoneMask extends TextInputFormatter {
  @override
  TextEditingValue formatEditUpdate(TextEditingValue oldValue, TextEditingValue newValue) {
    var d = newValue.text.replaceAll(RegExp(r'\D'), '');
    // Pasted "+7 701…" or "8 701…": keep the 10 local digits.
    if (d.length > 10 && (d.startsWith('7') || d.startsWith('8'))) d = d.substring(1);
    final m = maskLocal(d);
    return TextEditingValue(text: m, selection: TextSelection.collapsed(offset: m.length));
  }
}

/// 1c — the code from WhatsApp; signs in as soon as the last digit is typed.
class LoginCodeScreen extends StatefulWidget {
  const LoginCodeScreen({super.key, required this.phone});
  final String phone;

  static const codeLength = 6;

  @override
  State<LoginCodeScreen> createState() => _LoginCodeScreenState();
}

class _LoginCodeScreenState extends State<LoginCodeScreen> {
  final _ctl = TextEditingController();
  final _focus = FocusNode();
  bool _busy = false;
  String? _error;
  int _left = 60;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _tick();
  }

  void _tick() {
    _timer?.cancel();
    _left = 60;
    _timer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (!mounted) return t.cancel();
      setState(() => _left = _left > 0 ? _left - 1 : 0);
      if (_left == 0) t.cancel();
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    _ctl.dispose();
    _focus.dispose();
    super.dispose();
  }

  Future<void> _verify() async {
    final code = _ctl.text;
    if (code.length != LoginCodeScreen.codeLength || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await context.read<Session>().verifyCode(widget.phone, code);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e is ApiException && e.status == 401 && e.detail.isEmpty ? context.t.codeWrong : errorText(context, e);
        _ctl.clear();
      });
      _focus.requestFocus();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _resend() async {
    try {
      await context.read<Session>().requestCode(widget.phone);
      _tick();
      if (mounted) toast(context, context.t.codeResent);
    } catch (e) {
      if (mounted) toastError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final code = _ctl.text;
    return Scaffold(
      appBar: NavBar(backLabel: t.phoneShort),
      body: SafeArea(
        top: false,
        child: ListView(padding: const EdgeInsets.fromLTRB(24, 12, 24, 24), children: [
          Semantics(header: true, child: Text(t.codeTitle, style: display(24, color: oe.brandInk))),
          const SizedBox(height: 10),
          Text.rich(TextSpan(style: TextStyle(color: oe.muted, fontSize: 14.5), children: [
            TextSpan(text: '${t.codeSent} '),
            TextSpan(text: maskPhone(widget.phone), style: TextStyle(color: oe.ink, fontWeight: FontWeight.w600)),
          ])),
          const SizedBox(height: 20),
          GestureDetector(
            onTap: () => _focus.requestFocus(),
            child: Stack(children: [
              Row(children: [
                for (var i = 0; i < LoginCodeScreen.codeLength; i++) ...[
                  if (i > 0) const SizedBox(width: 8),
                  Expanded(
                    child: AnimatedContainer(
                      duration: context.motion(150),
                      height: 60,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: oe.surface,
                        borderRadius: BorderRadius.circular(OeStyle.ios ? 14 : 8),
                        border: Border.all(
                            color: _error != null ? oe.red : (i == code.length ? oe.primary : oe.line),
                            width: i == code.length ? 2 : 1),
                      ),
                      child: Text(i < code.length ? code[i] : '', style: display(24, color: oe.ink)),
                    ),
                  ),
                ],
              ]),
              // The real input sits under the boxes: native keyboard, paste and SMS/WhatsApp code autofill.
              Positioned.fill(
                child: Opacity(
                  opacity: 0.01,
                  child: TextField(
                    key: const Key('code'),
                    controller: _ctl,
                    focusNode: _focus,
                    autofocus: true,
                    keyboardType: TextInputType.number,
                    autofillHints: const [AutofillHints.oneTimeCode],
                    maxLength: LoginCodeScreen.codeLength,
                    showCursor: false,
                    enableInteractiveSelection: false,
                    inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                    decoration: const InputDecoration(counterText: '', border: InputBorder.none, filled: false),
                    onChanged: (_) {
                      setState(() => _error = null);
                      _verify();
                    },
                  ),
                ),
              ),
            ]),
          ),
          if (_error != null)
            Padding(padding: const EdgeInsets.only(top: 10), child: Text(_error!, style: TextStyle(color: oe.red, fontSize: 13))),
          const SizedBox(height: 14),
          Row(children: [
            Expanded(
              child: _left > 0
                  ? Text(t.codeAgainIn('0:${_left.toString().padLeft(2, '0')}'), style: TextStyle(fontSize: 13, color: oe.muted))
                  : Align(
                      alignment: Alignment.centerLeft,
                      child: GestureDetector(
                        onTap: _resend,
                        child: Text(t.codeAgain, style: TextStyle(fontSize: 13, color: oe.tint, fontWeight: FontWeight.w600)),
                      ),
                    ),
            ),
            if (_busy) const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
          ]),
        ]),
      ),
    );
  }
}
