<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiIcon, UiSegmented } from '@/components/ui'
import { keptRef } from '@/utils/kept'

/** «Дорожная карта»: the student's way through the levels, for adults (Beginner → Upper-Intermediate) and for
 *  children (Family & Friends 1–4). Texts are the school's own, in Russian and Kazakh. */
const { locale } = useI18n()
const kk = computed(() => locale.value === 'kk')
const L = (ru: string, kz: string) => (kk.value ? kz : ru)
const track = keptRef<'adults' | 'kids'>('roadmap.track', () => 'adults')

const ui = computed(() => ({
  title: L('Дорожная карта студента', 'Студенттің жол картасы'),
  adults: L('Взрослые', 'Ересектер'),
  kids: L('Дети', 'Балалар'),
  kidsTitle: L('Дорожная карта и учебный план изучения английского языка', 'Ағылшын тілін үйрену жол картасы және оқу жоспары'),
  start: L('Старт', 'Бастау'),
  finish: L('Финиш', 'Мәре'),
  months: L('мес.', 'ай'),
  total: L('Весь путь', 'Бүкіл жол'),
  words: L('слов', 'сөз'),
  test: L('Тест уровня', 'Деңгей тесті'),
  parents: L('Уважаемые родители!', 'Құрметті ата-аналар!'),
  motto: L('Шаг за шагом – к новым возможностям!', 'Қадам сайын – жаңа мүмкіндіктер!'),
}))
const tracks = computed(() => [{ value: 'adults' as const, label: ui.value.adults }, { value: 'kids' as const, label: ui.value.kids }])

const adults = computed(() => [
  {
    name: 'Beginner', months: 3, words: '500–600', icon: 'chat',
    text: L(
      'Вы научитесь строить простые предложения о себе и окружающем мире: говорить о хобби, повседневных делах и событиях прошлого. Ваш словарный запас пополнится на 500-600 базовых слов и выражений.',
      'Негізгі сөздер мен тіркестерді пайдаланып, өзіңіз және қоршаған орта туралы қарапайым сөйлемдер құрауды үйренесіз. Хобби, күнделікті әрекеттер, өткен шақтағы оқиғалар туралы айта аласыз. Сөздік қорыңыз 500-600 сөзге дейін жетеді.'),
  },
  {
    name: 'Elementary', months: 4, words: '+700–800', icon: 'book',
    text: L(
      'Ваш словарный запас пополнится ещё на 700-800 слов. Вы научитесь делиться планами на будущее, сравнивать, говорить о количестве, глубже освоите грамматику и сможете уверенно рассказывать о прошлом и делиться опытом.',
      'Сөздік қорыңыз тағы 700-800 сөзге толығады. Болашақ жоспарлар, салыстырулар, мөлшерлер және негізгі грамматикалық құрылымдар тереңірек меңгеріледі. Өткен оқиғалар туралы еркін сипаттап, өз тәжірибеңізбен бөлісе аласыз.'),
  },
  {
    name: 'Pre-Intermediate', months: 4, words: '+800–1000', icon: 'flag',
    text: L(
      'Ваш словарный запас увеличится ещё на 800-1000 слов. Вы сможете говорить о настоящем, прошлом и будущем, выражать мнение, давать советы, строить предположения и уверенно пересказывать чужие слова и истории.',
      'Тағы 800-1000 сөз бен тіркесті меңгересіз. Оқиғаларды логикалық байланыстыра отырып, осы, өткен және келер шақта сөйлей аласыз. Пікір білдіру, кеңес беру, болжам жасау және басқалардың сөздерін жеткізуге үйренесіз.'),
  },
  {
    name: 'Intermediate', months: 4, words: '+1200–1500', icon: 'idea',
    text: L(
      'Ваш словарный запас увеличится ещё на 1200-1500 слов. Вы научитесь анализировать сложные идеи, строить гипотезы, описывать людей и события в деталях, использовать Passive voice, объяснять связь прошлого и настоящего, участвовать в длительных дискуссиях и аргументировать свою точку зрения.',
      'Сөздік қорыңыз 1200-1500 сөзге дейін артады. Күрделі ойларды талдап, сценарийлер құрастырып, адамдар мен оқиғаларды егжей-тегжейлі сипаттай аласыз. Passive voice қолданасыз, өткен және осы шақтың байланысын түсіндіресіз, ұзақ пікірталастарға қатысып, өз көзқарасыңызды дәлелдей аласыз.'),
  },
  {
    name: 'Upper-Intermediate', months: 4, words: '+1500–2000', icon: 'progress',
    text: L(
      'Ваш словарный запас расширится ещё на 1500-2000 слов. Вы свободно используете идиомы, phrasal verbs и синонимы, увлекательно рассказываете истории, планируете будущее, анализируете прошлое с помощью past modals и используете reporting verbs для передачи чужих слов. Вы сможете легко аргументировать позицию в дискуссиях, понимать фильмы и блоги на английском и общаться с носителями языка без подготовки.',
      'Сөздік қорыңыз 1500-2000 сөзге дейін кеңейеді. Идиомаларды, phrasal verbs және синонимдерді еркін қолданасыз. Өткен шақтың барлық формаларын байланыстырып, болашақты дәл жоспарлап, past modals арқылы талдау жасайсыз. Репорттық етістіктерді (reporting verbs) еркін қолданасыз. Кез келген тақырыпта еркін пікір алмасып, шетелдіктермен табиғи сөйлесе аласыз.'),
  },
])
const adultTotal = computed(() => adults.value.reduce((n, s) => n + s.months, 0))
const adultNotes = computed(() => [
  {
    icon: 'tests',
    text: L('После прохождения каждого уровня студент сдаёт тест. При наборе проходного балла он переходит на следующий уровень.',
      'Әр деңгейді аяқтағаннан кейін студент тест тапсырады. Өткізу балын жинаған жағдайда, келесі деңгейге өтеді.'),
  },
  {
    icon: 'cal',
    text: L('При длительных перерывах (например, летние каникулы) ученик может забыть пройденный материал. В таком случае рекомендуется заново повторить пройденные темы.',
      'Ұзақ үзілістер кезінде (мысалы, жазғы каникулдарда) өткен материалдар ұмытылады. Мұндай жағдайда бұрын өткен тақырыптарды қайта қайталау ұсынылады.'),
  },
])

const kids = computed(() => [
  {
    name: 'Family & Friends 1', tone: 'rmk-g',
    sum: L('Базовый словарный запас, алфавит', 'Негізгі сөздік қор, әліпби'),
    topics: [
      { icon: 'abc', text: L('Алфавит и буквы', 'Әріптер мен дыбыстар') },
      { icon: 'book', text: L('Словарный запас', 'Сөздік қор') },
      { icon: 'dialog', text: L('Базовые разговорные фразы', 'Негізгі сөйлемдер') },
    ],
  },
  {
    name: 'Family & Friends 2', tone: 'rmk-b',
    sum: L('Важные слова, городская жизнь', 'Маңызды сөздер, қала өмірі'),
    topics: [
      { icon: 'notebook', text: L('Важные слова', 'Маңызды сөздер') },
      { icon: 'home', text: L('Городская жизнь', 'Қала өмірі') },
      { icon: 'star', text: L('Домашние животные', 'Үй жануарлары') },
      { icon: 'pencil', text: L('Хобби', 'Хоббилер') },
    ],
  },
  {
    name: 'Family & Friends 3', tone: 'rmk-p',
    sum: L('Прошедшие времена, будущие планы', 'Өткен шақтар, болашақ жоспарлар'),
    topics: [
      { icon: 'history', text: L('Прошедшие времена', 'Өткен шақтар') },
      { icon: 'calendar-add', text: L('Будущие планы', 'Болашақ жоспарлар') },
      { icon: 'level', text: L('Сравнения', 'Салыстыру') },
      { icon: 'graduation', text: L('Школьные предметы', 'Мектеп пәндері') },
    ],
  },
  {
    name: 'Family & Friends 4', tone: 'rmk-o',
    sum: L('Сложная грамматика, мир и путешествия', 'Күрделі грамматика, әлем және саяхат'),
    topics: [
      { icon: 'idea', text: L('Сложная грамматика', 'Күрделі грамматика') },
      { icon: 'globe', text: L('Мир и путешествия', 'Әлем және саяхат') },
      { icon: 'zap', text: L('Наука', 'Ғылым') },
      { icon: 'speaking', text: L('Выражение мнения', 'Пікір білдіру') },
    ],
  },
])
const kidsNote = computed(() => L(
  'Данная дорожная карта и учебный план составлены при условии полного и качественного прохождения всех книг. То есть, если ученик ответственно выполняет домашние задания и активно, старательно занимается на курсах, он сможет достичь указанных результатов. При длительных перерывах в обучении (например, во время летних каникул) ребенок может забыть пройденный материал и ему потребуется повторное изучение.',
  'Бұл жол картасы мен оқу жоспары барлық кітаптарды толық әрі үздік түрде меңгеру шартына құрылған. Яғни, егер оқушы үй тапсырмаларын жауапкершілікпен орындайтын және курстарда белсенді, ұқыпты түрде оқыса, көрсетілген нәтижелерге қол жеткізуге болады. Оқуда ұзақ үзілістер болса (мысалы, жазғы демалыс кезінде), бала өткен материалдарды ұмытып қалуы мүмкін және оларды қайта пысықтап, жаңадан үйренуге тура келуі ықтимал.'))
</script>

<template>
  <div class="rm">
    <div class="ph">
      <div><h1>{{ track === 'adults' ? ui.title : ui.kidsTitle }}</h1><p v-if="track === 'kids'">Family &amp; Friends 1 – Family &amp; Friends 4</p></div>
      <span class="sp" />
      <UiSegmented v-model="track" :options="tracks" :label="ui.title" />
    </div>

    <!-- the whole way at a glance -->
    <div class="rm-strip card" :class="track">
      <template v-if="track === 'adults'">
        <div v-for="(s, i) in adults" :key="s.name" class="rm-stop" :class="i % 2 ? 'rm-red' : 'rm-navy'">
          <span class="dot">{{ i + 1 }}</span>
          <b>{{ s.name }}</b>
          <small class="num">{{ s.months }} {{ ui.months }}</small>
        </div>
        <div class="rm-sum"><small>{{ ui.total }}</small><b class="num">{{ adultTotal }} {{ ui.months }}</b></div>
      </template>
      <template v-else>
        <div v-for="(s, i) in kids" :key="s.name" class="rm-stop" :class="s.tone">
          <span class="dot">{{ i + 1 }}</span>
          <b>{{ s.name }}</b>
          <small class="num">2,5 – 3 {{ ui.months }}</small>
        </div>
        <div class="rm-sum"><small>{{ ui.total }}</small><b class="num">10 – 12 {{ ui.months }}</b></div>
      </template>
    </div>

    <!-- the path -->
    <ol v-if="track === 'adults'" class="rm-path stagger">
      <li class="rm-cap"><span class="pin"><UiIcon name="play" :size="16" /></span><b>{{ ui.start }}</b></li>
      <li v-for="(s, i) in adults" :key="s.name" class="rm-step" :class="i % 2 ? 'rm-red' : 'rm-navy'">
        <span class="node"><UiIcon :name="s.icon" :size="24" /></span>
        <article class="card rm-card">
          <header>
            <span class="no num">{{ i + 1 }}</span>
            <h2>{{ s.name }}</h2>
            <span class="dur num"><UiIcon name="clock" :size="16" />{{ s.months }} {{ ui.months }}</span>
          </header>
          <p>{{ s.text }}</p>
          <footer>
            <span class="tag"><UiIcon name="book" :size="14" /><b class="num">{{ s.words }}</b> {{ ui.words }}</span>
            <span class="tag"><UiIcon name="tests" :size="14" />{{ ui.test }}</span>
          </footer>
        </article>
      </li>
      <li class="rm-cap end"><span class="pin"><UiIcon name="trophy" :size="16" /></span><b>{{ ui.finish }}</b></li>
    </ol>

    <ol v-else class="rm-path stagger">
      <li class="rm-cap"><span class="pin"><UiIcon name="play" :size="16" /></span><b>{{ ui.start }}</b></li>
      <li v-for="(s, i) in kids" :key="s.name" class="rm-step kid" :class="s.tone">
        <span class="node num">{{ i + 1 }}</span>
        <article class="card rm-card">
          <header>
            <h2>{{ s.name }}</h2>
            <span class="dur num"><UiIcon name="clock" :size="16" />2,5 – 3 {{ ui.months }}</span>
          </header>
          <div class="rm-topics">
            <span v-for="tp in s.topics" :key="tp.text" class="tp"><span class="ic"><UiIcon :name="tp.icon" :size="20" /></span>{{ tp.text }}</span>
          </div>
          <footer><b class="sum">{{ s.sum }}</b></footer>
        </article>
      </li>
      <li class="rm-cap end"><span class="pin"><UiIcon name="trophy" :size="16" /></span><b>{{ ui.finish }}</b></li>
    </ol>

    <div v-if="track === 'adults'" class="rm-notes">
      <div v-for="n in adultNotes" :key="n.icon" class="card rm-note"><span class="ic"><UiIcon :name="n.icon" :size="20" /></span><p>{{ n.text }}</p></div>
    </div>
    <div v-else class="card rm-note wide"><span class="ic"><UiIcon name="users" :size="20" /></span><div><b>{{ ui.parents }}</b><p>{{ kidsNote }}</p></div></div>

    <p class="rm-motto">{{ ui.motto }}</p>
  </div>
</template>

<style scoped>
.rm { max-width: 980px; margin: 0 auto }
.rm .ph h1 { text-wrap: balance }

.rm-strip { display: flex; align-items: stretch; gap: 0; padding: 14px 16px; margin-bottom: 22px; overflow-x: auto }
.rm-stop { flex: 1 1 0; min-width: 118px; display: flex; flex-direction: column; align-items: center; gap: 4px; text-align: center; position: relative; padding-top: 2px }
.rm-stop::before { content: ''; position: absolute; top: 15px; left: -50%; width: 100%; height: 3px; background: var(--line); z-index: 0 }
.rm-stop:first-child::before { display: none }
.rm-stop .dot { width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center; color: #fff; font-weight: 700; font-size: 14px; background: var(--c); position: relative; z-index: 1; box-shadow: 0 0 0 4px var(--surface) }
.rm-stop b { font-size: 13px; line-height: 1.2 }
.rm-stop small { color: var(--muted); font-size: 12px }
.rm-sum { flex: none; display: flex; flex-direction: column; justify-content: center; align-items: flex-end; gap: 2px; padding-left: 16px; margin-left: 8px; border-left: 1px solid var(--line); white-space: nowrap }
.rm-sum small { color: var(--muted); font-size: 12px }
.rm-sum b { font-size: 18px; font-family: var(--font-display) }

.rm-navy { --c: var(--navy); --c-bg: var(--navy-50) }
.rm-red { --c: var(--red); --c-bg: var(--red-100) }
.rmk-g { --c: #3f9b4b; --c-bg: color-mix(in srgb, #3f9b4b 13%, var(--surface)) }
.rmk-b { --c: #2f7fd1; --c-bg: color-mix(in srgb, #2f7fd1 13%, var(--surface)) }
.rmk-p { --c: #7a5bd0; --c-bg: color-mix(in srgb, #7a5bd0 13%, var(--surface)) }
.rmk-o { --c: #e08a1e; --c-bg: color-mix(in srgb, #e08a1e 15%, var(--surface)) }

.rm-path { list-style: none; margin: 0; padding: 0; position: relative }
.rm-path::before { content: ''; position: absolute; left: 31px; top: 14px; bottom: 14px; width: 0; border-left: 3px dashed var(--line) }
.rm-step { position: relative; display: grid; grid-template-columns: 64px 1fr; gap: 18px; align-items: start; padding: 10px 0 }
.rm-step .node { width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center; background: var(--c); color: #fff; position: relative; z-index: 1; box-shadow: 0 0 0 5px var(--bg, var(--surface)), 0 0 0 7px color-mix(in srgb, var(--c) 35%, transparent); font-size: 24px; font-weight: 700; font-family: var(--font-display) }
.rm-card { padding: 16px 18px; position: relative; width: 100%; min-width: 0; box-sizing: border-box; border-left: 4px solid var(--c) }
.rm-card::before { content: ''; position: absolute; left: -22px; top: 30px; width: 18px; height: 3px; background: var(--c); border-radius: 2px }
.rm-card header { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 8px }
.rm-card .no { width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center; background: var(--c); color: #fff; font-weight: 700; flex: none }
.rm-card h2 { margin: 0; font-family: var(--font-display); font-size: 20px; color: var(--c); flex: 1 1 auto }
.rm-step.rm-navy h2 { color: var(--ink) }
.rm-card .dur { display: inline-flex; align-items: center; gap: 6px; background: var(--c); color: #fff; font-weight: 600; font-size: 13.5px; padding: 5px 12px; border-radius: 999px; white-space: nowrap }
.rm-card p { margin: 0; line-height: 1.55; color: var(--ink) }
.rm-card footer { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px }
.rm-card .tag { display: inline-flex; align-items: center; gap: 6px; background: var(--c-bg); border-radius: 999px; padding: 4px 11px; font-size: 13px }
.rm-card .sum { font-size: 13px; text-transform: uppercase; letter-spacing: .03em; color: var(--c) }

.rm-step.kid .rm-card { background: var(--c-bg); border-color: transparent; border-left: 4px solid var(--c) }
.rm-step.kid h2 { color: var(--ink) }
.rm-topics { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px }
.rm-topics .tp { display: flex; align-items: center; gap: 10px; background: var(--surface); border-radius: 12px; padding: 9px 12px; font-weight: 600; font-size: 13.5px; line-height: 1.25 }
.rm-topics .ic { width: 38px; height: 38px; border-radius: 10px; display: grid; place-items: center; background: var(--c-bg); color: var(--c); flex: none }

.rm-cap { display: flex; align-items: center; gap: 12px; padding: 4px 0 4px 17px; position: relative; z-index: 1; color: var(--muted); font-size: 13px; text-transform: uppercase; letter-spacing: .06em }
.rm-cap .pin { width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center; background: var(--surface); border: 2px solid var(--line); color: var(--muted) }
.rm-cap.end .pin { background: var(--red); border-color: var(--red); color: #fff }
.rm-cap.end { color: var(--ink) }

.rm-notes { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 18px }
.rm-note { display: flex; gap: 12px; align-items: flex-start; padding: 14px 16px }
.rm-note.wide { margin-top: 18px }
.rm-note .ic { width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center; background: var(--navy-50); color: var(--accent-ink, var(--navy)); flex: none }
.rm-note p { margin: 0; line-height: 1.5; font-size: 14px }
.rm-note b { display: block; margin-bottom: 4px }
.rm-motto { text-align: center; font-family: var(--font-display); font-weight: 700; font-style: italic; font-size: 18px; color: var(--red-ink, var(--red)); margin: 26px 0 8px; text-wrap: balance }

@media (max-width: 700px) {
  .rm-path::before { left: 21px }
  .rm-step { grid-template-columns: 44px 1fr; gap: 12px }
  .rm-step .node { width: 44px; height: 44px; font-size: 18px }
  .rm-step .node :deep(svg) { width: 20px; height: 20px }
  .rm-card::before { left: -16px; width: 12px; top: 20px }
  .rm-card { padding: 13px 14px }
  .rm-card h2 { font-size: 17px }
  .rm-cap { padding-left: 7px }
  .rm-notes { grid-template-columns: 1fr }
  .rm-sum { display: none }
}
</style>
