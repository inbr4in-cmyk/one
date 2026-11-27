<script setup lang="ts">
import logo from '@/assets/brand/logo-tagline.svg'

/** The A5 sheet with a QR for a table stand. Every size is in `em`, so the caller scales it with font-size (1em = 1mm on paper). */
defineProps<{ qr: string; kk: string; ru: string; url: string }>()
</script>

<template>
  <div class="ps">
    <svg class="ps-deco tl" viewBox="0 0 60 60" aria-hidden="true"><circle cx="0" cy="0" r="26" /><circle cx="0" cy="0" r="40" /><circle cx="0" cy="0" r="54" /></svg>
    <svg class="ps-deco br" viewBox="0 0 60 60" aria-hidden="true"><circle cx="60" cy="60" r="26" /><circle cx="60" cy="60" r="40" /><circle cx="60" cy="60" r="54" /></svg>
    <div class="ps-dots tr" aria-hidden="true"><i v-for="i in 15" :key="i" /></div>
    <div class="ps-dots bl" aria-hidden="true"><i v-for="i in 15" :key="i" /></div>

    <img class="ps-logo" :src="logo" alt="One English" />
    <p class="ps-kk">{{ kk }}</p>
    <span class="ps-rule" aria-hidden="true"><b /></span>
    <p class="ps-ru">{{ ru }}</p>

    <div class="ps-qr">
      <span class="ps-c ps-ca" aria-hidden="true" /><span class="ps-c ps-cb" aria-hidden="true" /><span class="ps-c ps-cc" aria-hidden="true" /><span class="ps-c ps-cd" aria-hidden="true" />
      <img v-if="qr" :src="qr" alt="QR" />
    </div>

    <p class="ps-url">{{ url.replace(/^https?:\/\//, '') }}</p>
    <div class="ps-foot" aria-hidden="true"><b /><i /></div>
  </div>
</template>

<style scoped>
.ps { position: relative; width: 148em; height: 210em; background: #fff; color: #01225f; overflow: hidden; display: flex; flex-direction: column; align-items: center; padding: 13em 12em 0; box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact }
.ps-logo { height: 25em; width: auto; display: block }
.ps-kk, .ps-ru { margin: 0; text-align: center; font-family: var(--font-display); font-weight: 700; text-transform: uppercase; line-height: 1.2; letter-spacing: -.01em; text-wrap: balance; max-width: 124em }
.ps-kk { margin-top: 1.5em; font-size: 6.4em; color: #bb1027 }
.ps-ru { font-size: 5.2em; color: #01225f }
.ps-rule { display: flex; align-items: center; width: 60em; height: .6em; margin: 3.4em 0; background: #01225f; border-radius: 1em; position: relative }
.ps-rule b { position: absolute; left: 50%; top: 50%; width: 3em; height: 3em; margin: -1.5em 0 0 -1.5em; border-radius: 50%; background: #bb1027; box-shadow: 0 0 0 1.2em #fff }
.ps-qr { position: relative; margin-top: 7em; width: 104em; height: 104em; border-radius: 9em; background: #fff; border: .9em solid #01225f; padding: 7em; box-sizing: border-box; box-shadow: 0 3em 0 -1.2em #e8ecf5 }
.ps-qr img { width: 100%; height: 100%; display: block; image-rendering: pixelated }
.ps-c { position: absolute; width: 16em; height: 16em; border: 1.6em solid #bb1027; background: none }
.ps-ca { left: -3.4em; top: -3.4em; border-right: 0; border-bottom: 0; border-top-left-radius: 11em }
.ps-cb { right: -3.4em; top: -3.4em; border-left: 0; border-bottom: 0; border-top-right-radius: 11em }
.ps-cc { left: -3.4em; bottom: -3.4em; border-right: 0; border-top: 0; border-bottom-left-radius: 11em }
.ps-cd { right: -3.4em; bottom: -3.4em; border-left: 0; border-top: 0; border-bottom-right-radius: 11em }
.ps-url { margin: 2.4em 0 0; font-family: var(--font-ui); font-size: 3.1em; color: #5b6784; letter-spacing: .02em }
.ps-foot { position: absolute; left: 0; right: 0; bottom: 0; height: 5em; display: flex }
.ps-foot b { flex: 3; background: #01225f }
.ps-foot i { flex: 1; background: #bb1027 }
.ps-deco { position: absolute; width: 34em; height: 34em; fill: none; stroke: #01225f; stroke-width: .5; opacity: .22 }
.ps-deco.tl { left: 0; top: 0 }
.ps-deco.br { right: 0; bottom: 5em; stroke: #bb1027; opacity: .28 }
.ps-dots { position: absolute; display: grid; grid-template-columns: repeat(5, 1em); gap: 1.6em; opacity: .35 }
.ps-dots i { width: 1em; height: 1em; border-radius: 50%; background: #01225f }
.ps-dots.tr { right: 9em; top: 11em }
.ps-dots.bl { left: 9em; bottom: 13em }
.ps-dots.bl i { background: #bb1027 }
</style>
