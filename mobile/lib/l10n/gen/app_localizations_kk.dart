// ignore: unused_import
import 'package:intl/intl.dart' as intl;

import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Kazakh (`kk`).
class AppLocalizationsKk extends AppLocalizations {
  AppLocalizationsKk([String locale = 'kk']) : super(locale);

  @override
  String get back => 'Артқа';

  @override
  String get navHome => 'Басты';

  @override
  String get navSchedule => 'Кесте';

  @override
  String get navHomework => 'Тапсырма';

  @override
  String get navChats => 'Чаттар';

  @override
  String get navCoins => 'Коиндер';

  @override
  String get navPayments => 'Төлем';

  @override
  String get navNotifications => 'Хабарламалар';

  @override
  String get navProfile => 'Профиль';

  @override
  String get retry => 'Қайталау';

  @override
  String get cancel => 'Болдырмау';

  @override
  String get loading => 'Жүктелуде…';

  @override
  String get send => 'Жіберу';

  @override
  String get search => 'Іздеу';

  @override
  String get call => 'Қоңырау шалу';

  @override
  String get copy => 'Көшіру';

  @override
  String get copied => 'Көшірілді';

  @override
  String get remove => 'Алып тастау';

  @override
  String get understood => 'Түсінікті';

  @override
  String get notNow => 'Қазір емес';

  @override
  String get selected => 'Таңдалды';

  @override
  String get today => 'Бүгін';

  @override
  String get yesterday => 'Кеше';

  @override
  String get you => 'Сіз';

  @override
  String get school => 'Мектеп';

  @override
  String branchName(String name) {
    return '$name филиалы';
  }

  @override
  String get branchShort => 'Сіздің филиал';

  @override
  String get errGeneric => 'Бірдеңе дұрыс болмады. Қайталап көріңіз.';

  @override
  String get errNetwork => 'Сервермен байланыс жоқ. Интернетті тексеріңіз.';

  @override
  String get nothingFound => 'Ештеңе табылмады';

  @override
  String get wdMon => 'Дс';

  @override
  String get wdTue => 'Сс';

  @override
  String get wdWed => 'Ср';

  @override
  String get wdThu => 'Бс';

  @override
  String get wdFri => 'Жм';

  @override
  String get wdSat => 'Сн';

  @override
  String get wdSun => 'Жс';

  @override
  String get roleParent => 'Ата-ана';

  @override
  String get roleTeacher => 'Мұғалім';

  @override
  String get roleManager => 'Менеджер';

  @override
  String get roleAdmin => 'Әкімші';

  @override
  String get roleStaff => 'Мектеп';

  @override
  String get splashFoot => 'Ағылшын тілі мектебі · Шымкент';

  @override
  String get offlineTitle => 'Байланыс жоқ';

  @override
  String get offlineText =>
      'Сервермен байланыс орнамады. Интернетті тексеріп, қайталап көріңіз.';

  @override
  String get loginTitle => 'Кіру';

  @override
  String get loginText => 'Мектепке берген телефон нөміріңізді енгізіңіз.';

  @override
  String get phoneLabel => 'Телефон нөмірі';

  @override
  String get phoneInvalid => 'Нөмірді толық енгізіңіз: +7 және 10 сан';

  @override
  String get codeChannel => 'Кодты қайда жіберу керек';

  @override
  String get waFast => 'Ең жылдамы';

  @override
  String get smsSoon => 'Жақында';

  @override
  String get getCode => 'Код алу';

  @override
  String noNumber(String phone) {
    return 'Нөміріңіз мектепте жоқ па? WhatsApp-қа жазыңыз: $phone';
  }

  @override
  String get staffRejected =>
      'Бұл қосымша оқушылар мен ата-аналарға арналған. Қызметкерлер веб-кабинетте жұмыс істейді.';

  @override
  String get codeTitle => 'WhatsApp-тағы код';

  @override
  String get codeSent => '6 таңбалы кодты мына нөмірге жібердік';

  @override
  String get codeWrong => 'Код қате';

  @override
  String get codeAgain => 'Кодты қайта жіберу';

  @override
  String codeAgainIn(String time) {
    return '$time кейін қайта жіберу';
  }

  @override
  String get codeResent => 'Код қайта жіберілді';

  @override
  String get pinCreate => 'PIN-код ойлап табыңыз';

  @override
  String get pinCreateText =>
      'Жылдам кіру үшін 4 сан. Онсыз WhatsApp кодымен кіресіз.';

  @override
  String get pinRepeat => 'PIN-кодты қайталаңыз';

  @override
  String get pinMismatch => 'Кодтар сәйкес емес. Қайталап көріңіз.';

  @override
  String get pinWeak =>
      'Тым қарапайым код. 1111, 1234 немесе туған жылды қолданбаңыз.';

  @override
  String get pinHint => 'Код тек осы телефонда сақталады';

  @override
  String pinEnter(String name) {
    return 'Сәлеметсіз бе, $name';
  }

  @override
  String pinWrong(int n) {
    return 'Код қате. $n әрекет қалды';
  }

  @override
  String get pinForgot => 'Кодты ұмыттыңыз ба? Нөмір арқылы кіру';

  @override
  String get pinTooMany =>
      'Тым көп әрекет. Телефон нөмірі арқылы қайта кіріңіз.';

  @override
  String get pinChange => 'PIN-кодты өзгерту';

  @override
  String get pinSet => 'PIN-код орнату';

  @override
  String get pinChanged => 'PIN-код сақталды';

  @override
  String get pinOff => 'PIN-кодты өшіру';

  @override
  String get pinOffTitle => 'PIN-кодты өшіру керек пе?';

  @override
  String get pinOffText =>
      'Қосымша кодсыз ашылады. Биометрия арқылы кіру де өшеді.';

  @override
  String get erase => 'Өшіру';

  @override
  String get bioTitleIos => 'Face ID арқылы кіру керек пе?';

  @override
  String get bioTitleAndroid => 'Саусақ ізімен кіру керек пе?';

  @override
  String get bioText =>
      'Бұл PIN-кодтан жылдам. Код қосалқы тәсіл болып қалады.';

  @override
  String get bioEnableIos => 'Face ID қосу';

  @override
  String get bioEnableAndroid => 'Саусақ ізін қосу';

  @override
  String get bioUse => 'Биометриямен кіру';

  @override
  String get bioReason => 'One English-ке кіруді растаңыз';

  @override
  String get bioToggleIos => 'Face ID арқылы кіру';

  @override
  String get bioToggleAndroid => 'Саусақ ізімен кіру';

  @override
  String get autolock => 'Автобұғаттау';

  @override
  String get autolockText => 'Қосымшадан шыққаннан кейін PIN-код сұрау';

  @override
  String get autolockNow => 'Бірден';

  @override
  String minutesN(int n) {
    return '$n мин';
  }

  @override
  String get blockedTitle => 'Қолжетімділік тоқтатылды';

  @override
  String get blockedText =>
      'Сабақтар бітті, ал төлем түспеді. Төлегеннен кейін бәрі автоматты түрде ашылады.';

  @override
  String get blockedShort => 'Тоқтатылды';

  @override
  String get toPayments => 'Төлемге';

  @override
  String get noChildren => 'Әзірге балалар жоқ';

  @override
  String get noChildrenText =>
      'Мектеп балаңызды нөміріңізге әлі байланыстырмаған. Менеджерге жазыңыз.';

  @override
  String helloStudent(String name) {
    return 'Сәлем, $name!';
  }

  @override
  String helloParent(String name) {
    return 'Сәлеметсіз бе, $name';
  }

  @override
  String get nextLesson => 'Келесі сабақ';

  @override
  String get lessonNow => 'Қазір жүріп жатыр';

  @override
  String inDays(int n) {
    return '$n күннен кейін';
  }

  @override
  String inHoursMinutes(int h, int m) {
    return '$h сағ $m мин кейін';
  }

  @override
  String inMinutes(int m) {
    return '$m мин кейін';
  }

  @override
  String room(String room) {
    return '$room кабинет';
  }

  @override
  String get individualLesson => 'Жеке сабақ';

  @override
  String get lessonsLeft => 'Қалған сабақтар';

  @override
  String ofN(int n) {
    return '$n ішінен';
  }

  @override
  String heldN(int n) {
    return '$n сабақ өтті';
  }

  @override
  String perWeek(int n) {
    return 'аптада +$n';
  }

  @override
  String get myBalance => 'Менің коиндерім';

  @override
  String get hwToday => 'Бүгінгі тапсырмалар';

  @override
  String dueAt(String time) {
    return '$time дейін';
  }

  @override
  String hwCheckedGrade(int grade) {
    return 'Тексерілді · $grade';
  }

  @override
  String hwTodayAt(String time) {
    return 'Бүгін $time дейін';
  }

  @override
  String get allTasks => 'Барлық тапсырма';

  @override
  String get attendanceMonth => 'Айлық қатысу';

  @override
  String presentOf(int a, int b) {
    return '$b сабақтың $a қатысты';
  }

  @override
  String get debtTitle => 'Қарыз бар';

  @override
  String debtText(int n) {
    return '$n сабақ қарыз — балансты толтырыңыз';
  }

  @override
  String lowTitle(int n) {
    String _temp0 = intl.Intl.pluralLogic(
      n,
      locale: localeName,
      other: '$n сабақ қалды',
      zero: 'Сабақтар бітті',
    );
    return '$_temp0';
  }

  @override
  String get lowText => 'Сабақ үзілмес үшін балансты толтырыңыз';

  @override
  String get consentTitle => 'Сабақты жазуға келісім';

  @override
  String get consentText => '«Ережелер» бөлімінде келісімге қол қойыңыз';

  @override
  String get avgGrade => 'Орташа баға';

  @override
  String avgFor(String month, int n) {
    return '$month · $n баға';
  }

  @override
  String attendanceOf(String month) {
    return 'Қатысу · $month';
  }

  @override
  String nOfM(int a, int b) {
    return '$b ішінен $a';
  }

  @override
  String get stPresent => 'Келді';

  @override
  String get stLate => 'Кешікті';

  @override
  String get stAbsent => 'Келмеді';

  @override
  String get stExcused => 'Себепті';

  @override
  String get stAhead => 'Алда';

  @override
  String get progress => 'Үлгерім';

  @override
  String get myProgress => 'Менің жетістіктерім';

  @override
  String get monthLessons => 'Сабақ';

  @override
  String get monthPresent => 'Қатысты';

  @override
  String get monthRate => 'Қатысу';

  @override
  String get thisWeek => 'Осы апта';

  @override
  String get prevWeek => 'Өткен апта';

  @override
  String get nextWeek => 'Келесі апта';

  @override
  String get noLessons => 'Сабақ жоқ';

  @override
  String get noLessonsWeek => 'Осы аптада сабақ жоқ';

  @override
  String get cancelled => 'Болдырылмады';

  @override
  String cancelledOn(String day, String time) {
    return '$day $time сабағы болдырылмады';
  }

  @override
  String get held => 'Өтті';

  @override
  String get teacherComment => 'Мұғалімнің пікірі';

  @override
  String get rateLesson => 'Сабақты бағалаңыз';

  @override
  String get yourRating => 'Сіздің бағаңыз';

  @override
  String get rated => 'Бағаңызға рақмет!';

  @override
  String starsN(int n) {
    return '$n жұлдыз';
  }

  @override
  String get lessonGrades => 'Сабақ бағалары';

  @override
  String get hwActive => 'Белсенді';

  @override
  String hwActiveN(int n) {
    return 'Белсенді · $n';
  }

  @override
  String get hwReview => 'Тексерісте';

  @override
  String get hwChecked => 'Тексерілді';

  @override
  String get hwAssigned => 'Берілді';

  @override
  String get hwOverdue => 'Мерзімі өтті';

  @override
  String get hwSubmitted => 'Тапсырылды';

  @override
  String get hwNotSubmitted => 'Жауап тапсырылмады';

  @override
  String get hwNone => 'Әзірге бос';

  @override
  String get hwNoneActive => 'Барлық тапсырма орындалды';

  @override
  String get hwNotFound => 'Тапсырма табылмады';

  @override
  String get hwTask => 'Тапсырма';

  @override
  String dueFull(String date) {
    return '$date дейін тапсыру';
  }

  @override
  String get myAnswer => 'Менің жауабым';

  @override
  String get hwAnswerHint => 'Жауабыңызды жазыңыз…';

  @override
  String get hwOneFile => 'Бір файл тіркеуге болады: фото, дауыс немесе құжат';

  @override
  String get hwFile => 'Файл';

  @override
  String get hwSubmit => 'Тапсырманы тапсыру';

  @override
  String get hwSent => 'Тапсырма тексеруге жіберілді';

  @override
  String get hwRedo => 'Қайта орындау';

  @override
  String get hwNoAnswer => 'Жауап жазыңыз немесе файл тіркеңіз';

  @override
  String get hwNoAnswerParent => 'Оқушы бұл тапсырманы әлі тапсырмады';

  @override
  String get photo => 'Фото';

  @override
  String get camera => 'Камера';

  @override
  String get gallery => 'Галерея';

  @override
  String get voice => 'Дауыс';

  @override
  String get file => 'Файл';

  @override
  String get stop => 'Тоқтату';

  @override
  String get play => 'Тыңдау';

  @override
  String get pause => 'Кідірту';

  @override
  String get uploading => 'Файл жүктелуде…';

  @override
  String get micDenied =>
      'Микрофонға рұқсат жоқ. Телефон баптауларында рұқсат беріңіз.';

  @override
  String recording(String time) {
    return 'Жазу $time';
  }

  @override
  String get recordVoice => 'Дауыстық жазу';

  @override
  String get progressAndGrades => 'Үлгерім және бағалар';

  @override
  String get level => 'Деңгей';

  @override
  String get average => 'Орташа';

  @override
  String get noMarks => 'Әзірге баға жоқ';

  @override
  String get noTests => 'Әзірге тест болған жоқ';

  @override
  String get attendanceHistory => 'Қатысу тарихы';

  @override
  String get debt => 'Қарыз';

  @override
  String get notCharged => 'Есептен шығарылмады';

  @override
  String debtLessonsN(int n) {
    return '$n сабақ қарыз';
  }

  @override
  String pricePer(String price) {
    return 'Бір сабақ $price';
  }

  @override
  String get needPayment => 'Төлем қажет';

  @override
  String get howToPay => 'Қалай төлеуге болады';

  @override
  String get payHowText =>
      'Филиалда қолма-қол, картамен немесе аударыммен төлеуге болады. Қосымшада онлайн төлем кейінірек болады.';

  @override
  String get onlineSoon => 'Онлайн төлем жақында болады';

  @override
  String payFor(String name) {
    return '$name үшін төлем';
  }

  @override
  String callBranch(String name) {
    return '$name филиалына қоңырау шалу';
  }

  @override
  String get writeManager => 'Менеджерге жазу';

  @override
  String lessonsN(int n) {
    return '$n сабақ';
  }

  @override
  String onBalance(String sum) {
    return 'Балансда $sum';
  }

  @override
  String get history => 'Тарих';

  @override
  String get noPayments => 'Әзірге төлем жоқ';

  @override
  String refunded(String sum) {
    return 'Қайтарым $sum';
  }

  @override
  String payCategory(String c) {
    String _temp0 = intl.Intl.selectLogic(c, {
      'course': 'Курс',
      'book': 'Оқулық',
      'other': 'Төлем',
    });
    return '$_temp0';
  }

  @override
  String get payCash => 'Қолма-қол';

  @override
  String get payCard => 'Карта';

  @override
  String get payTransfer => 'Аударым';

  @override
  String get bookPurchase => 'Оқулық сатып алу';

  @override
  String get myBooks => 'Оқулықтар';

  @override
  String get noBooks => 'Әзірге оқулық жоқ';

  @override
  String get noBooksText => 'Мұнда мектептен сатып алынған оқулықтар көрінеді';

  @override
  String booksLevel(String level) {
    return '$level деңгейі';
  }

  @override
  String get chat => 'Чат';

  @override
  String get noChats => 'Әзірге чат жоқ';

  @override
  String get noChatsText =>
      'Мұғалімге немесе менеджерге жазыңыз — «Жаңа чат» батырмасын басыңыз';

  @override
  String get newChat => 'Жаңа чат';

  @override
  String get searchPeople => 'Аты бойынша іздеу';

  @override
  String get contactsHint =>
      'Өз топтарыңыздың мұғалімдеріне және филиал менеджерлеріне жазуға болады';

  @override
  String get noContacts => 'Жазатын адам жоқ';

  @override
  String membersN(int n) {
    return '$n қатысушы';
  }

  @override
  String get chatNotice =>
      'Хат алмасу мектепте сақталады. Құпиясөз бен карта нөмірін жібермеңіз.';

  @override
  String get chatRulesTitle => 'Чат ережелері';

  @override
  String get chatRule1 =>
      'Сыпайы сөйлесіңіз — хат алмасуды мектеп әкімшілігі көреді.';

  @override
  String get chatRule2 =>
      'Оқушыларға мұғалімдермен телефон нөмірлерін алмасуға болмайды.';

  @override
  String get chatRule3 =>
      'Бірдеңе дұрыс болмаса — хабарламаны басып, «Шағымдану» таңдаңыз.';

  @override
  String get noMessages => 'Әзірге хабарлама жоқ';

  @override
  String get firstMessage => 'Бірінші хабарламаны жазыңыз';

  @override
  String get message => 'Хабарлама';

  @override
  String get attach => 'Тіркеу';

  @override
  String get pinned => 'Бекітілген';

  @override
  String pinnedN(int n) {
    return 'Бекітілген · $n';
  }

  @override
  String get messageHidden => 'Хабарлама жасырылды';

  @override
  String get hideMessage => 'Жасыру';

  @override
  String get hideTitle => 'Хабарламаны жасыру керек пе?';

  @override
  String get hideText => 'Хабарлама чаттың барлық қатысушысынан жоғалады.';

  @override
  String get report => 'Шағымдану';

  @override
  String get reportWhy => 'Хабарламада не дұрыс емес?';

  @override
  String get reportHint => 'Шағымды мектеп әкімшілігі қарайды';

  @override
  String get reasonInsult => 'Дөрекілік немесе қорлау';

  @override
  String get reasonSpam => 'Спам немесе жарнама';

  @override
  String get reasonPersonal => 'Жеке байланыс сұрайды';

  @override
  String get reasonOther => 'Басқа';

  @override
  String reportSubject(String chat) {
    return '«$chat» чатындағы хабарламаға шағым';
  }

  @override
  String reportBody(
    String reason,
    String author,
    String at,
    String text,
    int id,
  ) {
    return 'Себебі: $reason\nАвторы: $author\nУақыты: $at\nХабарлама: $text\nХабарлама ID: $id';
  }

  @override
  String reportSent(String date) {
    return 'Шағым жіберілді. Жауап $date дейін';
  }

  @override
  String get phoneBlockedTitle => 'Хабарламада телефон нөмірі';

  @override
  String get phoneBlockedText =>
      'Оқушыларға мектеп чаттарында телефон нөмірін жіберуге болмайды. Жіберу үшін нөмірді алып тастаңыз.';

  @override
  String get phoneShort => 'Телефон нөмірін алып тастаңыз';

  @override
  String get removeNumber => 'Нөмірді алып тастау';

  @override
  String get shop => 'Дүкен';

  @override
  String get rating => 'Рейтинг';

  @override
  String get orders => 'Тапсырыстарым';

  @override
  String get exchange => 'Айырбастау';

  @override
  String get buyTitle => 'Коиндерді айырбастау керек пе?';

  @override
  String buyText(String item, String price) {
    return '«$item» — $price коин. Филиал әкімшісінен алуға болады.';
  }

  @override
  String ordered(String item) {
    return '«$item» тапсырысы рәсімделді';
  }

  @override
  String needMore(String n) {
    return '$n жетпейді';
  }

  @override
  String get outOfStock => 'Қоймада жоқ';

  @override
  String get shopEmpty => 'Дүкен әзірге бос';

  @override
  String openOrders(int n) {
    return '$n тапсырыс берілуін күтуде';
  }

  @override
  String groupN(String name) {
    return '$name тобы';
  }

  @override
  String get noRating => 'Рейтинг әзірге бос';

  @override
  String get noCoinHistory => 'Әзірге есептеу жоқ';

  @override
  String get coinAward => 'Есептеу';

  @override
  String coinOrder(String item) {
    return 'Айырбас: $item';
  }

  @override
  String get coinOrderCancelled => 'Болдырылмаған тапсырыс үшін қайтарым';

  @override
  String coinsN(int n) {
    return '$n коин';
  }

  @override
  String get noOrders => 'Әзірге тапсырыс жоқ';

  @override
  String get orderPlaced => 'Рәсімделді';

  @override
  String get orderPlacedHint => 'Әкімші сыйлықты дайындайды';

  @override
  String get orderReady => 'Беруге дайын';

  @override
  String get orderReadyHint => 'Филиал әкімшісінен алыңыз';

  @override
  String get orderIssued => 'Берілді';

  @override
  String get orderCancelled => 'Тапсырыс болдырылмады, коиндер қайтарылды';

  @override
  String get orderCancelledShort => 'Болдырылмады';

  @override
  String get pickUp => 'Алу';

  @override
  String get cancelOrder => 'Тапсырысты болдырмау';

  @override
  String get cancelOrderTitle => 'Тапсырысты болдырмау керек пе?';

  @override
  String cancelOrderText(String item, int coins) {
    return '«$item» — $coins коин балансқа қайтады.';
  }

  @override
  String get trioLeft => 'сабақ';

  @override
  String get trioCoins => 'коин';

  @override
  String get trioStars => 'жұлдыз';

  @override
  String get feedback => 'Шағымдар мен ұсыныстар';

  @override
  String get feedbackSubtitle =>
      'Нені жақсартуға болатынын жазыңыз. 3 жұмыс күні ішінде жауап береміз.';

  @override
  String get feedbackNew => 'Жаңа өтініш';

  @override
  String get subject => 'Тақырып';

  @override
  String get subjectHint => 'Мәні туралы қысқаша';

  @override
  String get subjectRequired => 'Тақырыпты көрсетіңіз (3 таңбадан)';

  @override
  String get complaintBody => 'Толығырақ';

  @override
  String get complaintBodyHint => 'Не болды, қашан және кіммен';

  @override
  String get bodyRequired => 'Толығырақ сипаттаңыз (10 таңбадан)';

  @override
  String get against => 'Мұғалім туралы';

  @override
  String get againstHint =>
      'Өтініш мұғалім туралы болса — оны таңдаңыз, өтініш оған емес, басшылыққа жіберіледі';

  @override
  String get nobody => 'Нақты адам туралы емес';

  @override
  String teacherOf(String name) {
    return 'Мұғалім $name';
  }

  @override
  String get feedbackNote => 'Өтінішті тек мектеп басшылары көреді.';

  @override
  String complaintSent(String date) {
    return 'Өтініш жіберілді. Жауап $date дейін';
  }

  @override
  String get feedbackHistory => 'Менің өтініштерім';

  @override
  String get feedbackEmpty => 'Әзірге өтініш жоқ';

  @override
  String get feedbackEmptyText =>
      'Мұнда шағымдарыңыз бен ұсыныстарыңыз жауаптарымен көрінеді';

  @override
  String sentAt(String date) {
    return '$date жіберілді';
  }

  @override
  String dueAnswer(String date) {
    return 'жауап $date дейін';
  }

  @override
  String get answer => 'Мектеп жауабы';

  @override
  String get appeal => 'Жауаппен келіспеймін';

  @override
  String get appealTitle => 'Жауапқа шағымдану керек пе?';

  @override
  String get appealText => 'Өтініш операциялық директорға жіберіледі.';

  @override
  String get appealed => 'Операциялық директорға жіберілді';

  @override
  String get cNew => 'Жаңа';

  @override
  String get cAcknowledged => 'Қабылданды';

  @override
  String get cInvestigating => 'Қаралуда';

  @override
  String get cAnswered => 'Жауап бар';

  @override
  String get cAppealed => 'Шағымданылды';

  @override
  String get cClosed => 'Жабылды';

  @override
  String get rulesTitle => 'Ережелер мен келісімдер';

  @override
  String get rulesGateTitle => 'Мектеп ережелері';

  @override
  String get rulesUpdated => 'Ережелер жаңартылды';

  @override
  String rulesGateText(String version, String date) {
    return 'Жалғастыру үшін ережелерді оқып, қабылдаңыз ($version нұсқа, $date бастап күшінде).';
  }

  @override
  String get rulesAgree => 'Ережелерді оқыдым және келісемін';

  @override
  String get rulesAccept => 'Ережелерді қабылдау';

  @override
  String rulesAcceptedV(String version) {
    return 'Сіз ережелерді қабылдадыңыз, $version нұсқа';
  }

  @override
  String get tabRules => 'Ережелер';

  @override
  String get tabRecording => 'Сабақты жазу';

  @override
  String get recordingParent =>
      'Сабақтар сапаны бақылау үшін жазылуы мүмкін. Әр бала үшін келісімге қол қойыңыз.';

  @override
  String get recordingSelf =>
      'Сабақтар сапаны бақылау үшін жазылуы мүмкін. Келісіміңізді растаңыз.';

  @override
  String get recordingHint =>
      'Келісімді кез келген уақытта қайтарып алуға болады';

  @override
  String get notSigned => 'Қол қойылмаған';

  @override
  String signedAt(String date) {
    return '$date қол қойылды';
  }

  @override
  String get sign => 'Қол қою';

  @override
  String get revoke => 'Қайтарып алу';

  @override
  String get revokeTitle => 'Келісімді қайтарып алу керек пе?';

  @override
  String get revokeText => 'Мектеп бала қатысатын сабақтарды жазуды тоқтатады.';

  @override
  String get revoked => 'Келісім қайтарылды';

  @override
  String get consentSaved => 'Сақталды';

  @override
  String get docNotPublished => 'Құжат әлі жарияланбаған';

  @override
  String docVersion(String version, String date) {
    return '$version нұсқа · $date бастап';
  }

  @override
  String docUpcoming(String version, String date) {
    return '$date бастап $version нұсқа күшіне енеді';
  }

  @override
  String get fAll => 'Барлығы';

  @override
  String get fAttendance => 'Қатысу';

  @override
  String get fPayments => 'Төлемдер';

  @override
  String get fStudy => 'Оқу';

  @override
  String get noNotifications => 'Хабарлама жоқ';

  @override
  String get language => 'Тіл';

  @override
  String get theme => 'Тақырып';

  @override
  String get themeLight => 'Ашық';

  @override
  String get themeDark => 'Қараңғы';

  @override
  String get themeSystem => 'Авто';

  @override
  String get security => 'Қауіпсіздік';

  @override
  String get securitySub => 'PIN-код, биометрия, құрылғылар';

  @override
  String get logout => 'Шығу';

  @override
  String get logoutTitle => 'Аккаунттан шығу керек пе?';

  @override
  String get logoutText => 'Қайта кіру үшін WhatsApp коды қажет болады.';

  @override
  String get devices => 'Құрылғылар';

  @override
  String get devicesHint =>
      'Бейтаныс құрылғыны көрсеңіз — оның сеансын аяқтап, менеджерге жазыңыз.';

  @override
  String get thisDevice => 'Осы құрылғы';

  @override
  String get endSession => 'Аяқтау';

  @override
  String get endOthers => 'Басқа сеанстарды аяқтау';

  @override
  String get endOthersText =>
      'Басқа барлық құрылғыларда қайта кіру қажет болады.';

  @override
  String get unknownDevice => 'Белгісіз құрылғы';

  @override
  String get appDevice => 'One English қосымшасы';

  @override
  String get web => 'Браузер';
}
