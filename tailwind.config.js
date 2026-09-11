/** @type {import('tailwindcss').Config} */
// Theme derived from Sukoon_Design_System.pdf §10.2, with radius/shadow values
// taken literally from docs/design/sukoon_prototype.html (ADR-0006: the prototype
// is the literal source of truth for colour, radius and shadow).
module.exports = {
  content: ["./sukoon/templates/**/*.html"],
  theme: {
    extend: {
      colors: {
        ink: "#1C1C1E",
        inkSoft: "#48484D",
        muted: "#86868B",
        faint: "#B9B9BE",
        hairline: "#E8E7E3",
        paper: "#FAF9F6",
        surface: "#FFFFFF",
        sunk: "#F2F1EC",
        teal: {
          DEFAULT: "#0E6B57",
          deep: "#0A4F41",
          tint: "#E7F3EF",
          tint2: "#D6ECE4",
        },
        amber: { DEFAULT: "#B8873B", tint: "#FBF3E4" },
        coral: { DEFAULT: "#C15B45", tint: "#FBEEEA" },
        sky: { DEFAULT: "#3E6FBF", tint: "#EAF1FC" },
      },
      borderRadius: {
        sm: "11px",
        md: "16px",
        lg: "22px",
        pill: "999px",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
      boxShadow: {
        // from the prototype's cards, panels and controls
        card: "0 1px 1px rgba(0,0,0,0.02), 0 8px 22px rgba(0,0,0,0.045)",
        soft: "0 1px 1px rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.035)",
        teal: "0 8px 20px rgba(14,107,87,0.25)",
        control: "0 1px 3px rgba(0,0,0,0.06)",
      },
    },
  },
  plugins: [],
};
