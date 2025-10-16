/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#f8fafc",
        card: "#ffffff",
        border: "hsl(214 32% 91%)",
      },
      boxShadow: { soft: "0 2px 10px rgba(0,0,0,0.06)" },
      borderRadius: { xl: "1rem", "2xl": "1.25rem" },
    },
  },
  plugins: [],
}
