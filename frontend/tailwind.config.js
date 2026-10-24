/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#00C300",
          dark: "#009900",
          light: "#E6F9E6",
        },
      },
    },
  },
  plugins: [],
};
