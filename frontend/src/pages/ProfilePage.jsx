import { useAuth } from '../context/AuthContext';

function ProfilePage() {
  const { user } = useAuth();

  return (
    <div className="page-content">
      <div className="page-header">
        <div>
          <p className="eyebrow">Profile</p>
          <h1>{user?.name || 'Investor Profile'}</h1>
        </div>
      </div>

      <div className="panel profile-panel">
        <div className="profile-row">
          <span className="label">Name</span>
          <strong>{user?.name || 'Smart Investor'}</strong>
        </div>
        <div className="profile-row">
          <span className="label">Email</span>
          <strong>{user?.email || 'investor@smartinvest.ai'}</strong>
        </div>
        <div className="profile-row">
          <span className="label">Plan</span>
          <strong>Premium AI Strategy</strong>
        </div>
        <div className="profile-row">
          <span className="label">Risk Appetite</span>
          <strong>Balanced Growth</strong>
        </div>
      </div>
    </div>
  );
}

export default ProfilePage;
