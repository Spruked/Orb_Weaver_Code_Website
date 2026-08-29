declare module 'bcryptjs' {
  export function hashSync(s: string, salt?: number | string): string;
  export function hash(s: string, salt: number | string): Promise<string>;
  export function hash(s: string, salt: number | string, callback: (err: Error, hash: string) => void): void;
  
  export function compareSync(s: string, hash: string): boolean;
  export function compare(s: string, hash: string): Promise<boolean>;
  export function compare(s: string, hash: string, callback: (err: Error, same: boolean) => void): void;
  
  export function genSaltSync(rounds?: number): string;
  export function genSalt(rounds?: number): Promise<string>;
  export function genSalt(rounds: number, callback: (err: Error, salt: string) => void): void;
  export function genSalt(callback: (err: Error, salt: string) => void): void;
  
  export function getRounds(hash: string): number;
  export function getSalt(hash: string): string;
}
