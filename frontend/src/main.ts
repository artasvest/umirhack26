import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import { initThemeFromStorage } from "./composables/useTheme";
import "./style.css";

initThemeFromStorage();
createApp(App).use(router).mount("#app");
