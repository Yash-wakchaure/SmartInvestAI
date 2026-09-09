import { Link, NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

function Navbar() {
  const { user, logout, isAuthenticated } = useAuth();

  return (
    <header className="navbar">
      <div className="brand-wrap">
        <Link to="/dashboard" className="brand">
          SmartInvest AI
        </Link>
      </div>

      <div className="nav-actions">
        <div className="search-box">
          <span>Search</span>
        </div>
        <button className="ghost-btn" type="button">
          Notifications
        </button>
        <NavLink to="/profile" className="nav-profile">
          {user?.name || 'Profile'}
        </NavLink>
        {isAuthenticated && (
          <button className="nav-logout" type="button" onClick={logout}>
            Logout
          </button>
        )}
      </div>
    </header>
  );
}

export default Navbar;
