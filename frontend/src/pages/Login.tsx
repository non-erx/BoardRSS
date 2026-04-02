import { useState } from 'react'
import { setup, login } from '../api'

interface Props {
  isSetup: boolean
  onSuccess: () => void
}

export default function Login({ isSetup, onSuccess }: Props) {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (isSetup) {
      if (password.length < 4) {
        setError('Password must be at least 4 characters')
        return
      }
      if (password !== confirm) {
        setError('Passwords do not match')
        return
      }
    }

    setLoading(true)
    try {
      if (isSetup) {
        await setup(password)
      } else {
        await login(password)
      }
      onSuccess()
    } catch (err: any) {
      setError(err.message || 'Failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-wrapper">
      <form className="login-card" onSubmit={handleSubmit}>
        <h1 className="login-title">
          {isSetup ? 'Create Admin Account' : 'Login'}
        </h1>
        {isSetup && (
          <p className="login-subtitle">
            Set a password to protect your admin panel
          </p>
        )}
        <input
          className="admin-input"
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
          required
        />
        {isSetup && (
          <input
            className="admin-input"
            type="password"
            placeholder="Confirm password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
          />
        )}
        {error && (
          <div className="login-error">{error}</div>
        )}
        <button
          className="admin-btn admin-btn-primary login-btn"
          type="submit"
          disabled={loading}
        >
          {loading ? 'Please wait…' : isSetup ? 'Create Account' : 'Log In'}
        </button>
      </form>
    </div>
  )
}
