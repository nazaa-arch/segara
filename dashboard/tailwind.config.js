/** @type {import('tailwindcss').Config} */

// Palet brand SEGARA (lihat Logo/SEGARA Ocean Brand Guideline Board.png):
//   Deep Ocean Blue #0756A5 · Marine Blue #0798D5 · Aqua #45C5E8
//   Coral Red #F04435 · Warning Orange #FFAA24 · Neutral #0F2D4A / #F5F8FC
// Skala bawaan Tailwind dipetakan ulang ke turunan warna brand agar seluruh
// kelas yang sudah ada (slate, cyan, teal, rose, ...) otomatis mengikuti brand.

const navy = {          // netral: turunan #0F2D4A (pengganti slate)
  50: '#F5F8FC', 100: '#EBF1F8', 200: '#D7E2EE', 300: '#B5C8DB', 400: '#8DA7C2',
  500: '#6687A8', 600: '#456C91', 700: '#2A5277', 800: '#1A3D5F', 900: '#0F2D4A', 950: '#071A2E',
}
const marine = {        // Marine Blue #0798D5, Aqua #45C5E8, Deep Ocean #0756A5
  50: '#EAF8FD', 100: '#CDEFFA', 200: '#A6E3F6', 300: '#8ADCF2', 400: '#45C5E8',
  500: '#0798D5', 600: '#0679B0', 700: '#0756A5', 800: '#08478A', 900: '#0A3A6E', 950: '#082A52',
}
const aqua = {          // aksen aqua untuk gradien
  50: '#ECFAFE', 100: '#D3F3FB', 200: '#BDEBF8', 300: '#8ADCF2', 400: '#5FD0EE',
  500: '#45C5E8', 600: '#1FA9D4', 700: '#1287B0', 800: '#126B8C', 900: '#125873', 950: '#0A3647',
}
const coral = {         // Coral Red #F04435
  50: '#FEF2F1', 100: '#FDE2DF', 200: '#FCC4BE', 300: '#F99A91', 400: '#F4695D',
  500: '#F04435', 600: '#D93224', 700: '#B3261C', 800: '#8C1F18', 900: '#6B1A15', 950: '#3D0D0A',
}
const warning = {       // Warning Orange #FFAA24
  50: '#FFF8EB', 100: '#FFF0D4', 200: '#FFE1AA', 300: '#FFCF7A', 400: '#FFBB4D',
  500: '#FFAA24', 600: '#E08A0A', 700: '#B86C08', 800: '#8F540A', 900: '#6E410C', 950: '#3E2306',
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
        sans: ['Poppins', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
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
          coral: '#F04435',
          orange: '#FFAA24',
          navy: '#0F2D4A',
          mist: '#F5F8FC',
        },
        ocean: marine,
        coral,
      },
    },
  },
  plugins: [],
}
