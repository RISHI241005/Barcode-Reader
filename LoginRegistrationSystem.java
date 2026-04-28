import java.awt.BorderLayout;
import java.awt.CardLayout;
import java.awt.Color;
import java.awt.FlowLayout;
import java.awt.Font;
import java.awt.GridLayout;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Base64;
import javax.swing.BorderFactory;
import javax.swing.ButtonGroup;
import javax.swing.JButton;
import javax.swing.JCheckBox;
import javax.swing.JComboBox;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JOptionPane;
import javax.swing.JPanel;
import javax.swing.JPasswordField;
import javax.swing.JRadioButton;
import javax.swing.JTextField;
import javax.swing.SwingUtilities;
import javax.swing.UIManager;

public class LoginRegistrationSystem extends JFrame {
    private static final String DRIVER = "com.mysql.cj.jdbc.Driver";
    private static final String DB_URL =
            "jdbc:mysql://localhost:3306/login_system_db?createDatabaseIfNotExist=true&serverTimezone=UTC";
    private static final String DB_USERNAME = "root";
    private static final String DB_PASSWORD = "Rishi@042405";

    private final CardLayout cardLayout = new CardLayout();
    private final JPanel cardPanel = new JPanel(cardLayout);

    private JTextField loginUsernameField;
    private JPasswordField loginPasswordField;

    private JTextField fullNameField;
    private JTextField registerUsernameField;
    private JTextField emailField;
    private JPasswordField registerPasswordField;
    private JPasswordField confirmPasswordField;
    private JRadioButton maleRadioButton;
    private JRadioButton femaleRadioButton;
    private JComboBox<String> departmentComboBox;

    public LoginRegistrationSystem() {
        setTitle("Login and Registration System");
        setSize(650, 450);
        setLocationRelativeTo(null);
        setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        setLayout(new BorderLayout());

        createDatabaseTable();

        JLabel headingLabel = new JLabel("Java Swing Login & Registration System", JLabel.CENTER);
        headingLabel.setFont(new Font("Arial", Font.BOLD, 22));
        headingLabel.setBorder(BorderFactory.createEmptyBorder(15, 10, 10, 10));

        cardPanel.add(createLoginPanel(), "LOGIN");
        cardPanel.add(createRegisterPanel(), "REGISTER");

        add(headingLabel, BorderLayout.NORTH);
        add(cardPanel, BorderLayout.CENTER);

        cardLayout.show(cardPanel, "LOGIN");
    }

    private JPanel createLoginPanel() {
        JPanel panel = new JPanel(new BorderLayout());
        panel.setBorder(BorderFactory.createEmptyBorder(15, 30, 20, 30));

        JPanel formPanel = new JPanel(new GridLayout(4, 2, 10, 10));
        formPanel.setBorder(BorderFactory.createTitledBorder("Login"));

        loginUsernameField = new JTextField();
        loginPasswordField = new JPasswordField();

        JCheckBox showPasswordCheckBox = new JCheckBox("Show Password");
        showPasswordCheckBox.addActionListener(event ->
                loginPasswordField.setEchoChar(showPasswordCheckBox.isSelected() ? (char) 0 : '*'));

        formPanel.add(new JLabel("Username:"));
        formPanel.add(loginUsernameField);
        formPanel.add(new JLabel("Password:"));
        formPanel.add(loginPasswordField);
        formPanel.add(new JLabel(""));
        formPanel.add(showPasswordCheckBox);

        JButton loginButton = new JButton("Login");
        loginButton.setBackground(new Color(66, 133, 244));
        loginButton.setForeground(Color.WHITE);
        loginButton.addActionListener(event -> loginUser());

        JButton goToRegisterButton = new JButton("Create New Account");
        goToRegisterButton.addActionListener(event -> cardLayout.show(cardPanel, "REGISTER"));

        JPanel buttonPanel = new JPanel(new FlowLayout());
        buttonPanel.add(loginButton);
        buttonPanel.add(goToRegisterButton);

        panel.add(formPanel, BorderLayout.CENTER);
        panel.add(buttonPanel, BorderLayout.SOUTH);

        return panel;
    }

    private JPanel createRegisterPanel() {
        JPanel panel = new JPanel(new BorderLayout());
        panel.setBorder(BorderFactory.createEmptyBorder(15, 30, 20, 30));

        JPanel formPanel = new JPanel(new GridLayout(8, 2, 10, 10));
        formPanel.setBorder(BorderFactory.createTitledBorder("Registration"));

        fullNameField = new JTextField();
        registerUsernameField = new JTextField();
        emailField = new JTextField();
        registerPasswordField = new JPasswordField();
        confirmPasswordField = new JPasswordField();

        maleRadioButton = new JRadioButton("Male");
        femaleRadioButton = new JRadioButton("Female");

        ButtonGroup genderGroup = new ButtonGroup();
        genderGroup.add(maleRadioButton);
        genderGroup.add(femaleRadioButton);

        JPanel genderPanel = new JPanel(new FlowLayout(FlowLayout.LEFT));
        genderPanel.add(maleRadioButton);
        genderPanel.add(femaleRadioButton);

        String[] departments = {"Select Department", "BCA", "BSc IT", "BTech", "MCA", "Other"};
        departmentComboBox = new JComboBox<>(departments);

        JCheckBox showPasswordsCheckBox = new JCheckBox("Show Passwords");
        showPasswordsCheckBox.addActionListener(event -> {
            char echoChar = showPasswordsCheckBox.isSelected() ? (char) 0 : '*';
            registerPasswordField.setEchoChar(echoChar);
            confirmPasswordField.setEchoChar(echoChar);
        });

        formPanel.add(new JLabel("Full Name:"));
        formPanel.add(fullNameField);
        formPanel.add(new JLabel("Username:"));
        formPanel.add(registerUsernameField);
        formPanel.add(new JLabel("Email:"));
        formPanel.add(emailField);
        formPanel.add(new JLabel("Gender:"));
        formPanel.add(genderPanel);
        formPanel.add(new JLabel("Department:"));
        formPanel.add(departmentComboBox);
        formPanel.add(new JLabel("Password:"));
        formPanel.add(registerPasswordField);
        formPanel.add(new JLabel("Confirm Password:"));
        formPanel.add(confirmPasswordField);
        formPanel.add(new JLabel(""));
        formPanel.add(showPasswordsCheckBox);

        JButton registerButton = new JButton("Register");
        registerButton.setBackground(new Color(15, 157, 88));
        registerButton.setForeground(Color.WHITE);
        registerButton.addActionListener(event -> registerUser());

        JButton backButton = new JButton("Back to Login");
        backButton.addActionListener(event -> cardLayout.show(cardPanel, "LOGIN"));

        JLabel noteLabel = new JLabel(
                "Password must contain upper, lower, digit and special character.",
                JLabel.CENTER
        );

        JPanel buttonPanel = new JPanel(new FlowLayout());
        buttonPanel.add(registerButton);
        buttonPanel.add(backButton);

        JPanel bottomPanel = new JPanel(new BorderLayout());
        bottomPanel.add(noteLabel, BorderLayout.NORTH);
        bottomPanel.add(buttonPanel, BorderLayout.SOUTH);

        panel.add(formPanel, BorderLayout.CENTER);
        panel.add(bottomPanel, BorderLayout.SOUTH);

        return panel;
    }

    private Connection getConnection() throws SQLException, ClassNotFoundException {
        Class.forName(DRIVER);
        return DriverManager.getConnection(DB_URL, DB_USERNAME, DB_PASSWORD);
    }

    private void createDatabaseTable() {
        String createTableQuery =
                "CREATE TABLE IF NOT EXISTS users ("
                        + "id INT PRIMARY KEY AUTO_INCREMENT, "
                        + "full_name VARCHAR(100) NOT NULL, "
                        + "username VARCHAR(50) NOT NULL UNIQUE, "
                        + "email VARCHAR(100) NOT NULL UNIQUE, "
                        + "gender VARCHAR(10) NOT NULL, "
                        + "department VARCHAR(50) NOT NULL, "
                        + "password_hash VARCHAR(255) NOT NULL, "
                        + "salt VARCHAR(255) NOT NULL)";

        try (Connection connection = getConnection();
             Statement statement = connection.createStatement()) {
            statement.executeUpdate(createTableQuery);
        } catch (ClassNotFoundException exception) {
            JOptionPane.showMessageDialog(this, "MySQL JDBC driver not found.");
        } catch (SQLException exception) {
            JOptionPane.showMessageDialog(this, "Database connection error: " + exception.getMessage());
        }
    }

    private void registerUser() {
        String fullName = fullNameField.getText().trim();
        String username = registerUsernameField.getText().trim();
        String email = emailField.getText().trim();
        String gender = getSelectedGender();
        String department = getSelectedDepartment();
        String password = new String(registerPasswordField.getPassword());
        String confirmPassword = new String(confirmPasswordField.getPassword());

        String validationMessage = validateRegistration(
                fullName, username, email, gender, department, password, confirmPassword
        );

        if (validationMessage != null) {
            JOptionPane.showMessageDialog(this, validationMessage, "Registration Error", JOptionPane.ERROR_MESSAGE);
            return;
        }

        String checkUserQuery = "SELECT id FROM users WHERE username = ? OR email = ?";
        String insertUserQuery =
                "INSERT INTO users(full_name, username, email, gender, department, password_hash, salt) "
                        + "VALUES (?, ?, ?, ?, ?, ?, ?)";

        try {
            String salt = generateSalt();
            String passwordHash = hashPassword(password, salt);

            try (Connection connection = getConnection();
                 PreparedStatement checkStatement = connection.prepareStatement(checkUserQuery);
                 PreparedStatement insertStatement = connection.prepareStatement(insertUserQuery)) {

                checkStatement.setString(1, username);
                checkStatement.setString(2, email);

                try (ResultSet resultSet = checkStatement.executeQuery()) {
                    if (resultSet.next()) {
                        JOptionPane.showMessageDialog(this, "Username or email already exists.");
                        return;
                    }
                }

                insertStatement.setString(1, fullName);
                insertStatement.setString(2, username);
                insertStatement.setString(3, email);
                insertStatement.setString(4, gender);
                insertStatement.setString(5, department);
                insertStatement.setString(6, passwordHash);
                insertStatement.setString(7, salt);

                int rows = insertStatement.executeUpdate();
                if (rows > 0) {
                    JOptionPane.showMessageDialog(this, "Registration successful. Please login.");
                    clearRegistrationForm();
                    cardLayout.show(cardPanel, "LOGIN");
                }
            }
        } catch (ClassNotFoundException exception) {
            JOptionPane.showMessageDialog(this, "MySQL JDBC driver not found.");
        } catch (SQLException exception) {
            JOptionPane.showMessageDialog(this, "Registration failed: " + exception.getMessage());
        }
    }

    private void loginUser() {
        String username = loginUsernameField.getText().trim();
        String password = new String(loginPasswordField.getPassword());

        if (username.isEmpty() || password.isEmpty()) {
            JOptionPane.showMessageDialog(this, "Please enter username and password.");
            return;
        }

        String loginQuery = "SELECT full_name, password_hash, salt FROM users WHERE username = ?";

        try (Connection connection = getConnection();
             PreparedStatement statement = connection.prepareStatement(loginQuery)) {

            statement.setString(1, username);

            try (ResultSet resultSet = statement.executeQuery()) {
                if (resultSet.next()) {
                    String fullName = resultSet.getString("full_name");
                    String storedHash = resultSet.getString("password_hash");
                    String storedSalt = resultSet.getString("salt");
                    String enteredHash = hashPassword(password, storedSalt);

                    if (storedHash.equals(enteredHash)) {
                        JOptionPane.showMessageDialog(this, "Welcome " + fullName + ". Login successful.");
                        loginUsernameField.setText("");
                        loginPasswordField.setText("");
                    } else {
                        JOptionPane.showMessageDialog(this, "Invalid password.");
                    }
                } else {
                    JOptionPane.showMessageDialog(this, "User not found.");
                }
            }
        } catch (ClassNotFoundException exception) {
            JOptionPane.showMessageDialog(this, "MySQL JDBC driver not found.");
        } catch (SQLException exception) {
            JOptionPane.showMessageDialog(this, "Login failed: " + exception.getMessage());
        }
    }

    private String validateRegistration(String fullName, String username, String email,
                                        String gender, String department,
                                        String password, String confirmPassword) {
        if (fullName.isEmpty() || username.isEmpty() || email.isEmpty()
                || gender.isEmpty() || department.isEmpty()
                || password.isEmpty() || confirmPassword.isEmpty()) {
            return "All fields are required.";
        }

        if (!email.matches("^[A-Za-z0-9+_.-]+@[A-Za-z0-9.-]+$")) {
            return "Enter a valid email address.";
        }

        if (password.length() < 8) {
            return "Password must be at least 8 characters.";
        }

        if (!password.matches(".*[A-Z].*")) {
            return "Password must contain at least one uppercase letter.";
        }

        if (!password.matches(".*[a-z].*")) {
            return "Password must contain at least one lowercase letter.";
        }

        if (!password.matches(".*\\d.*")) {
            return "Password must contain at least one digit.";
        }

        if (!password.matches(".*[!@#$%^&*()].*")) {
            return "Password must contain at least one special character.";
        }

        if (!password.equals(confirmPassword)) {
            return "Password and confirm password do not match.";
        }

        return null;
    }

    private String getSelectedGender() {
        if (maleRadioButton.isSelected()) {
            return "Male";
        }
        if (femaleRadioButton.isSelected()) {
            return "Female";
        }
        return "";
    }

    private String getSelectedDepartment() {
        String department = (String) departmentComboBox.getSelectedItem();
        if ("Select Department".equals(department)) {
            return "";
        }
        return department;
    }

    private void clearRegistrationForm() {
        fullNameField.setText("");
        registerUsernameField.setText("");
        emailField.setText("");
        registerPasswordField.setText("");
        confirmPasswordField.setText("");
        maleRadioButton.setSelected(false);
        femaleRadioButton.setSelected(false);
        departmentComboBox.setSelectedIndex(0);
    }

    private String generateSalt() {
        byte[] salt = new byte[16];
        new SecureRandom().nextBytes(salt);
        return Base64.getEncoder().encodeToString(salt);
    }

    private String hashPassword(String password, String salt) {
        try {
            MessageDigest messageDigest = MessageDigest.getInstance("SHA-256");
            byte[] hashBytes = messageDigest.digest((password + salt).getBytes(StandardCharsets.UTF_8));
            return Base64.getEncoder().encodeToString(hashBytes);
        } catch (Exception exception) {
            throw new RuntimeException("Error while hashing password.");
        }
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> {
            try {
                UIManager.setLookAndFeel(UIManager.getSystemLookAndFeelClassName());
            } catch (Exception exception) {
                System.out.println("Default look and feel will be used.");
            }

            LoginRegistrationSystem frame = new LoginRegistrationSystem();
            frame.setVisible(true);
        });
    }
}

/* Commands to run the code in terminal 

javac -cp "lib\mysql-connector-j-8.4.0.jar" -d out LoginRegistrationSystem.java
java -cp "out;lib\mysql-connector-j-8.4.0.jar" LoginRegistrationSystem

*/

