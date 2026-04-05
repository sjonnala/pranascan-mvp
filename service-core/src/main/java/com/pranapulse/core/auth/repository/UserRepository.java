package com.pranapulse.core.auth.repository;

import com.pranapulse.core.auth.domain.User;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserRepository extends JpaRepository<User, UUID> {

    Optional<User> findByOidcSubject(String oidcSubject);

    Optional<User> findByEmailIgnoreCase(String email);
}
