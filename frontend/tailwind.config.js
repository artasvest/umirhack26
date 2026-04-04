/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
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
          300: "#c4c5cd",
          400: "#9a9ca8",
          500: "#6e707b",
          600: "#52545e",
          700: "#3d3f48",
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
        glow: "0 0 0 1px rgba(201, 169, 98, 0.2), 0 10px 40px rgba(201, 169, 98, 0.12), 0 24px 64px rgba(15, 16, 20, 0.1)",
        "glow-sm": "0 0 0 1px rgba(201, 169, 98, 0.15), 0 6px 24px rgba(201, 169, 98, 0.08)",
      },
      backgroundImage: {
        "mesh-light":
          "radial-gradient(900px circle at 0% -10%, rgba(201, 169, 98, 0.16), transparent 55%), radial-gradient(700px circle at 100% 0%, rgba(213, 214, 219, 0.45), transparent 50%), radial-gradient(600px circle at 50% 100%, rgba(201, 169, 98, 0.08), transparent 45%)",
        "mesh-dark":
          "radial-gradient(800px circle at 0% 0%, rgba(201, 169, 98, 0.12), transparent 50%), radial-gradient(700px circle at 100% 30%, rgba(61, 63, 72, 0.6), transparent 55%), radial-gradient(500px circle at 50% 100%, rgba(201, 169, 98, 0.06), transparent 40%)",
      },
    },
  },
  plugins: [],
};
