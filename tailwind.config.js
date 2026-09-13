/**
 * SMU brand palette mapped to semantic roles (see docs/PROGRESS.md UI-redesign
 * entry for the contrast checks behind these pairings). Raw brand hexes only
 * appear here — templates use the semantic names.
 */
module.exports = {
  content: [
    "./app/web/templates/**/*.html",
  ],
  theme: {
    extend: {
      colors: {
        // Primary action color / links / focus rings.
        primary: {
          DEFAULT: "#0075C9",
          hover: "#007EA4",
          light: "#E5F1FA",
        },
        // Secondary / accent color (teal). Raw teal fails AA for white text
        // (2.72:1) — `accent` is for surfaces/icons/borders with dark text on
        // top, `accent-dark` is the accessible-on-white variant for text/links.
        accent: {
          DEFAULT: "#00AFAA",
          dark: "#00726F",
          light: "#E1F6F5",
        },
        // Positive / finalized / success states.
        success: {
          DEFAULT: "#006450",
          light: "#86C057",
          tint: "#EEF7E4",
          "tint-text": "#3F5E1E",
        },
        // Needs-review / caution states. Amber fails AA for white text
        // (1.75:1) at any size — never pair `warning.DEFAULT` with white text.
        warning: {
          DEFAULT: "#FFB700",
          tint: "#FFF3D6",
          "tint-text": "#7A4B00",
        },
        // Failed / destructive states.
        danger: {
          DEFAULT: "#EC0044",
          hover: "#C40039",
          tint: "#FDE7EC",
          "tint-text": "#9A1240",
        },
        // Sparing accents only — badges/highlights, never primary UI chrome.
        purple: {
          DEFAULT: "#572F87",
          tint: "#F1EAF8",
        },
        pink: {
          DEFAULT: "#FB7598",
          tint: "#FEE7ED",
          "tint-text": "#9A1240",
        },
        // Custom cool-neutral scale (slight blue undertone to sit next to
        // `primary` instead of Tailwind's stock slate/gray).
        gray: {
          50: "#F7F8FA",
          100: "#EEF0F3",
          200: "#DFE3E8",
          300: "#C7CDD6",
          400: "#A3ACB9",
          500: "#7C8797",
          600: "#5C6675",
          700: "#434B57",
          800: "#2B313A",
          900: "#1A1D21",
          950: "#101215",
        },
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
