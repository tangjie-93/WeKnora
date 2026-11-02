import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { clearAuth, setAuth } from '../api'
export const useAppStore = defineStore('app', () => { const loggedIn = ref(Boolean(sessionStorage.getItem('weknora_token'))); const user = ref(''); const authenticated = computed(() => loggedIn.value); function signedIn(email: string, token: string, tenant: number) { setAuth(token, tenant); user.value = email; loggedIn.value = true } function signOut() { clearAuth(); loggedIn.value = false } return { authenticated, user, signedIn, signOut } })
