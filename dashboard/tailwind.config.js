/** @type {import('tailwindcss').Config} */

// Palet brand SEGARA (lihat Logo/SEGARA Brand Guideline Board.png):
//   Navy #0B2A44 (utama) · Blue #0756A5 (sekunder) · Cyan #0798D5 (aksen)
//   Orange #FF8A1F · Coral #EB505B · Yellow #FFD84D (highlight)
//   Aqua #45C5E8 dan netral #F5F8FC dipertahankan sebagai turunan pendukung.
// Skala bawaan Tailwind dipetakan ulang ke turunan warna brand agar seluruh
// kelas yang sudah ada (slate, cyan, teal, rose, ...) otomatis mengikuti brand.

const navy = {          // netral: turunan Navy #0B2A44 (pengganti slate)
  50: '#F5F8FC', 100: '#EBF1F8', 200: '#D7E2EE', 300: '#B5C8DB', 400: '#8DA7C2',
  500: '#6687A8', 600: '#456C91', 700: '#2A5277', 800: '#1A3D5F', 900: '#0B2A44', 950: '#071A2E',
}
const marine = {        // Marine Blue #0798D5, Aqua #45C5E8, Deep Ocean #0756A5
  50: '#EAF8FD', 100: '#CDEFFA', 200: '#A6E3F6', 300: '#8ADCF2', 400: '#45C5E8',
  500: '#0798D5', 600: '#0679B0', 700: '#0756A5', 800: '#08478A', 900: '#0A3A6E', 950: '#082A52',
}
const aqua = {          // aksen aqua untuk gradien
  50: '#ECFAFE', 100: '#D3F3FB', 200: '#BDEBF8', 300: '#8ADCF2', 400: '#5FD0EE',
  500: '#45C5E8', 600: '#1FA9D4', 700: '#1287B0', 800: '#126B8C', 900: '#125873', 950: '#0A3647',
}
const coral = {         // Coral #EB505B
  50: '#FDF1F2', 100: '#FCE3E5', 200: '#F9C7CB', 300: '#F5A4AA', 400: '#F07A82',
  500: '#EB505B', 600: '#CF4650', 700: '#A43840', 800: '#7F2B31', 900: '#5E2024', 950: '#341214',
}
const warning = {       // Orange #FF8A1F
  50: '#FFF6ED', 100: '#FFECDB', 200: '#FFDAB7', 300: '#FFC28B', 400: '#FFA655',
  500: '#FF8A1F', 600: '#E0791B', 700: '#B26116', 800: '#8A4B11', 900: '#66370C', 950: '#381E07',
}
const deepCoral = {     // Alert Level 2: coral gelap (pengganti magenta/pink)
  50: '#FCEDEC', 100: '#F8D6D3', 200: '#EFADA7', 300: '#E37B72', 400: '#D9534A',
  500: '#B3261C', 600: '#9A2018', 700: '#8C1F18', 800: '#5E1510', 900: '#47100C', 950: '#2A0907',
}
const ocean = {         // pengganti ungu: turunan Deep Ocean Blue
  50: '#EDF4FC', 100: '#D5E5F7', 200: '#AECDEF', 300: '#7FB0E3', 400: '#4A8DD6',
  500: '#0756A5', 600: '#064A8F', 700: '#063F7A', 800: '#0A3F7A', 900: '#082F5C', 950: '#061F3D',
}

export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Montserrat', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      colors: {
        slate: navy,
        cyan: marine,
        sky: marine,
        teal: aqua,
        rose: coral,
        red: coral,
        orange: warning,
        amber: warning,
        pink: deepCoral,
        purple: ocean,
        brand: {
          deep: '#0756A5',
          marine: '#0798D5',
          aqua: '#45C5E8',
          coral: '#EB505B',
          orange: '#FF8A1F',
          yellow: '#FFD84D',
          navy: '#0B2A44',
          mist: '#F5F8FC',
        },
        ocean: marine,
        coral,
      },
    },
  },
  plugins: [],
}
