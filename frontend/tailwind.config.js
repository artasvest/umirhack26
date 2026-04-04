/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["DM Sans", "system-ui", "sans-serif"],
        display: ["Outfit", "system-ui", "sans-serif"],
      },
      colors: {
        ink: {
          50: "#f7f7f8",
          100: "#ececee",
          200: "#d5d6db",
          800: "#2b2d35",
          900: "#1a1b20",
          950: "#0f1014",
        },
        accent: {
          DEFAULT: "#c9a962",
          dim: "#a68b4e",
        },
      },
      boxShadow: {
        card: "0 4px 24px rgba(15, 16, 20, 0.08)",
        lift: "0 12px 40px rgba(15, 16, 20, 0.12)",
      },
    },
  },
  plugins: [],
};
