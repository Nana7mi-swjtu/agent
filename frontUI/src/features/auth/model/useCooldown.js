import { onBeforeUnmount, ref } from "vue";

export const useCooldown = () => {
  const cooldown = ref(0);
  let timer = null;

  const clear = () => {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  };

  const start = (seconds) => {
    const value = Number(seconds) || 0;
    cooldown.value = value;
    clear();
    if (value <= 0) {
      return;
    }
    timer = setInterval(() => {
      cooldown.value -= 1;
      if (cooldown.value <= 0) {
        clear();
      }
    }, 1000);
  };

  onBeforeUnmount(clear);

  return {
    cooldown,
    start,
  };
};
