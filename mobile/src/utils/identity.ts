import AsyncStorage from '@react-native-async-storage/async-storage';

export const USER_ID_KEY = '@pranascan:user_id';

function generateUserId(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export async function getOrCreateUserId(): Promise<string> {
  let userId = await AsyncStorage.getItem(USER_ID_KEY);
  if (!userId) {
    userId = generateUserId();
    await AsyncStorage.setItem(USER_ID_KEY, userId);
  }
  return userId;
}
